from flask import current_app
from shopifyapp.models.store import Store
from shopifyapp.models.prompt import Prompt
from datetime import datetime
import jinja2
from typing import Dict, List, Optional, Tuple, Union, Any
from shopifyapp.models import Product
import shopify
from google.generativeai import GenerativeModel
import google.generativeai as genai
from celery import shared_task
from shopifyapp.models.job_status import JobStatus
from shopifyapp.services.crud_service import CRUD
from shopifyapp.exceptions import ResourceNotFoundError, ValidationError, DuplicateResourceError, JobInProgressError, APIError

class PromptService:
    @staticmethod
    def get_prompt_preferences(store_id: int, user_id: int) -> Tuple[Dict[str, Any], int]:
        """
        Get prompt preferences for a store.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains prompt preferences or error
                status_code: 200 for success, 404 for not found
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404
            
            return {'prompt_preferences': store.prompt_preferences}, 200
        except Exception as e:
            return {'error': str(e)}, 500

    @staticmethod
    def update_prompt_preferences(store_id: int, user_id: int, preferences: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Update prompt preferences for a store.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            preferences: New preferences including tone, style, etc.

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success message and updated preferences
                status_code: 200 for success, 404/400 for errors

        Raises:
            Exception: If update fails
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                raise ResourceNotFoundError("Store not found")

            # Validate required fields
            required_fields = ['tone', 'target_audience', 'writing_style']
            missing_fields = [field for field in required_fields if field not in preferences]
            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Merge existing preferences with new ones
            updated_preferences = store.prompt_preferences.copy() if store.prompt_preferences else {}
            for field in preferences:
                if field in ['brand_voice', 'industry_specific'] and isinstance(preferences[field], dict):
                    if field not in updated_preferences:
                        updated_preferences[field] = {}
                    updated_preferences[field].update(preferences[field])
                else:
                    updated_preferences[field] = preferences[field]

            # Use CRUD update and commit
            CRUD.update(Store, {'id': store_id}, {
                'prompt_preferences': updated_preferences,
                'updated_at': datetime.utcnow()
            })
            CRUD.db_commit()

            return {
                'message': 'Prompt preferences updated successfully',
                'prompt_preferences': updated_preferences
            }, 200

        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'store_id': store_id,
                'preferences': preferences
            })
            return {'error': str(e)}, 400
        except ResourceNotFoundError as e:
            current_app.logger.warning(f"Resource not found: {str(e)}", extra={
                'store_id': store_id,
                'user_id': user_id
            })
            return {'error': str(e)}, 404
        except Exception as e:
            current_app.logger.error(f"Failed to update preferences: {str(e)}", extra={
                'store_id': store_id,
                'error_type': type(e).__name__
            })
            CRUD.db_rollback()
            return {'error': 'An unexpected error occurred'}, 500

    @staticmethod
    def get_prompts(store_id: int, user_id: int) -> Tuple[Dict[str, Union[str, List[Dict[str, Any]]]], int]:
        """
        Get all prompts for a store.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains list of prompts or error
                status_code: 200 for success, 404 for not found
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404

            prompts = Prompt.query.filter_by(store_id=store_id).all()
            return {'prompts': [prompt.to_dict() for prompt in prompts]}, 200
        except Exception as e:
            return {'error': str(e)}, 500

    @staticmethod
    def get_prompt(store_id: int, user_id: int, prompt_id: int) -> Tuple[Dict[str, Any], int]:
        """
        Get a specific prompt.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            prompt_id: ID of the prompt to retrieve

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains prompt data or error
                status_code: 200 for success, 404 for not found
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404

            prompt = Prompt.query.filter_by(id=prompt_id, store_id=store_id).first()
            if not prompt:
                return {'error': 'Prompt not found'}, 404

            return {'prompt': prompt.to_dict()}, 200
        except Exception as e:
            return {'error': str(e)}, 500

    @staticmethod
    def create_prompt(store_id: int, user_id: int, prompt_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Create a new prompt.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            prompt_data: Prompt details including name, template, etc.

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success message and created prompt
                status_code: 201 for created, 404/400 for errors

        Raises:
            Exception: If creation fails or template syntax is invalid
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                raise ResourceNotFoundError(f"Store not found with ID: {store_id}")

            # Validate required fields
            required_fields = ['name', 'template']
            missing_fields = [field for field in required_fields if field not in prompt_data]
            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Validate template syntax
            try:
                jinja2.Template(prompt_data['template'])
            except Exception as e:
                raise ValidationError(f"Invalid template syntax: {str(e)}")

            # Check for duplicate prompt name
            existing_prompt = Prompt.query.filter_by(store_id=store_id, name=prompt_data['name']).first()
            if existing_prompt:
                raise DuplicateResourceError(f"Prompt with name '{prompt_data['name']}' already exists")

            # Prepare data for creation
            prompt_data.update({
                'store_id': store_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })
            
            prompt = CRUD.create(Prompt, prompt_data)
            CRUD.db_commit()
            
            return {'message': 'Prompt created successfully', 'prompt': prompt.to_dict()}, 201

        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'store_id': store_id,
                'prompt_data': prompt_data
            })
            return {'error': str(e)}, 400

        except ResourceNotFoundError as e:
            current_app.logger.warning(f"Resource not found: {str(e)}", extra={
                'store_id': store_id,
                'user_id': user_id
            })
            return {'error': str(e)}, 404

        except DuplicateResourceError as e:
            current_app.logger.warning(f"Duplicate resource: {str(e)}", extra={
                'store_id': store_id,
                'prompt_name': prompt_data.get('name')
            })
            return {'error': str(e)}, 409

        except Exception as e:
            current_app.logger.error(f"Unexpected error creating prompt: {str(e)}", extra={
                'store_id': store_id,
                'error_type': type(e).__name__,
                'error_details': str(e)
            })
            CRUD.db_rollback()
            return {'error': 'An unexpected error occurred'}, 500

    @staticmethod
    def update_prompt(store_id: int, user_id: int, prompt_id: int, prompt_data: dict) -> tuple:
        """
        Update an existing prompt.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            prompt_id: ID of the prompt to update
            prompt_data: Updated prompt details

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success message and updated prompt
                status_code: 200 for success, 404/400 for errors

        Raises:
            Exception: If update fails or template syntax is invalid
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404

            prompt = Prompt.query.filter_by(id=prompt_id, store_id=store_id).first()
            if not prompt:
                return {'error': 'Prompt not found'}, 404

            # Validate template syntax if provided
            if 'template' in prompt_data:
                try:
                    jinja2.Template(prompt_data['template'])
                except Exception as e:
                    return {'error': f'Invalid template syntax: {str(e)}'}, 400

            # Update fields
            updateable_fields = [
                'name', 'description', 'template', 'is_default', 'is_active',
                'variables', 'tone', 'target_audience', 'writing_style',
                'seo_keywords_focus', 'description_length', 'key_features',
                'brand_voice', 'industry_specific', 'custom_instructions',
                'example_description', 'avoid_words', 'must_include_elements',
                'template_sections'
            ]

            for field in updateable_fields:
                if field in prompt_data:
                    setattr(prompt, field, prompt_data[field])

            # Add updated_at to the data
            prompt_data['updated_at'] = datetime.utcnow()
            
            # Use CRUD update
            CRUD.update(Prompt, {'id': prompt_id, 'store_id': store_id}, prompt_data)
            CRUD.db_commit()

            return {'message': 'Prompt updated successfully', 'prompt': prompt.to_dict()}, 200

        except Exception as e:
            CRUD.db_rollback()
            return {'error': str(e)}, 500

    @staticmethod
    def delete_prompt(store_id: int, user_id: int, prompt_id: int) -> tuple:
        """
        Delete a prompt.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            prompt_id: ID of the prompt to delete

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success message or error
                status_code: 200 for success, 404/400 for errors

        Raises:
            Exception: If deletion fails
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                raise ResourceNotFoundError("Store not found")

            prompt = Prompt.query.filter_by(id=prompt_id, store_id=store_id).first()
            if not prompt:
                raise ResourceNotFoundError("Prompt not found")

            if prompt.is_default:
                raise ValidationError("Cannot delete default prompt")

            # Use CRUD delete instead of direct delete and commit
            CRUD.delete(Prompt, {'id': prompt_id, 'store_id': store_id})
            CRUD.db_commit()

            return {'message': 'Prompt deleted successfully'}, 200

        except ResourceNotFoundError as e:
            current_app.logger.warning(f"Resource not found: {str(e)}", extra={
                'store_id': store_id,
                'prompt_id': prompt_id
            })
            return {'error': str(e)}, 404
        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'prompt_id': prompt_id
            })
            return {'error': str(e)}, 400
        except Exception as e:
            current_app.logger.error(f"Failed to delete prompt: {str(e)}", extra={
                'store_id': store_id,
                'prompt_id': prompt_id,
                'error_type': type(e).__name__
            })
            CRUD.db_rollback()
            return {'error': 'An unexpected error occurred'}, 500

    @staticmethod
    def render_prompt(prompt: Prompt, context: Dict[str, Any]) -> str:
        """
        Render a prompt template with given context.

        Parameters:
            prompt: Prompt object containing the template
            context: Variables to render in the template

        Returns:
            Rendered prompt text

        Raises:
            Exception: If template rendering fails
        """
        try:
            template = jinja2.Template(prompt.template)
            return template.render(**context)
        except Exception as e:
            raise Exception(f"Failed to render prompt template: {str(e)}")

    @staticmethod
    def render_prompt_preview(template_str: str, context: Dict[str, Any]) -> str:
        """
        Preview a prompt template with sample data.

        Parameters:
            template_str: Template string to render
            context: Variables to render in the template

        Returns:
            Rendered preview text

        Raises:
            Exception: If preview rendering fails
        """
        try:
            # Add default values for missing context
            default_context: Dict[str, Any] = {
                'product_title': 'Sample Product',
                'original_description': 'This is a sample product description.',
                'tone': 'professional',
                'target_audience': 'general',
                'writing_style': 'descriptive',
                'seo_keywords_focus': 'balanced',
                'description_length': 'medium',
                'key_features': ['Feature 1', 'Feature 2'],
                'brand_voice': {
                    'personality': 'professional',
                    'emotion': 'neutral',
                    'formality': 'formal'
                },
                'industry_specific': {
                    'industry': 'General',
                    'technical_level': 'moderate'
                }
            }

            # Merge provided context with defaults
            merged_context = {**default_context, **context}

            # Render template
            template = jinja2.Template(template_str)
            return template.render(**merged_context)
        except Exception as e:
            raise Exception(f"Failed to preview prompt template: {str(e)}")

    @staticmethod
    def get_available_options() -> Tuple[Dict[str, Union[List[str], Dict[str, List[str]]]], int]:
        """
        Get available options for prompt preferences.

        Returns:
            tuple: (options_dict, status_code)
                options_dict: Contains all available options for prompts
                status_code: 200 for success
        """
        return {
            'tones': [
                'professional', 'casual', 'friendly', 'formal', 'technical',
                'conversational', 'enthusiastic', 'authoritative'
            ],
            'target_audiences': [
                'general', 'technical', 'business', 'casual', 'luxury',
                'budget-conscious', 'professionals', 'enthusiasts'
            ],
            'writing_styles': [
                'descriptive', 'technical', 'persuasive', 'informative',
                'narrative', 'comparative', 'minimalist'
            ],
            'seo_keywords_focus': [
                'balanced', 'aggressive', 'minimal', 'natural'
            ],
            'description_lengths': [
                'short', 'medium', 'long', 'comprehensive'
            ],
            'brand_voice_options': {
                'personality': [
                    'professional', 'friendly', 'expert', 'innovative',
                    'traditional', 'luxurious', 'playful'
                ],
                'emotion': [
                    'neutral', 'positive', 'excited', 'confident',
                    'empathetic', 'passionate'
                ],
                'formality': [
                    'formal', 'semi-formal', 'casual', 'conversational'
                ]
            },
            'technical_levels': [
                'basic', 'moderate', 'advanced', 'expert'
            ],
            'template_sections': [
                'introduction', 'key_features', 'benefits', 'specifications',
                'use_cases', 'testimonials', 'call_to_action', 'warranty_info',
                'shipping_info', 'care_instructions'
            ]
        }, 200

    @staticmethod
    def generate_selective_prompts(store_id: int, user_id: int, record_ids: List[int], prompt_type: str):
        try:
            if not record_ids:
                raise ValidationError("No record IDs provided")

            # Check for existing in-progress job
            existing_job = JobStatus.query.filter_by(
                store_id=store_id,
                job_type='generate',
                prompt_type=prompt_type,
                status='in_progress'
            ).first()

            if existing_job:
                raise JobInProgressError(f"Generation already in progress (Job ID: {existing_job.id})")

            # Validate store exists
            store = Store.query.get(store_id)
            if not store:
                raise ResourceNotFoundError(f"Store not found with ID: {store_id}")

            # Validate records exist
            records = Product.query.filter(
                Product.store_id == store_id,
                Product.id.in_(record_ids)
            ).all()
            if len(records) != len(record_ids):
                missing_ids = set(record_ids) - set(r.id for r in records)
                raise ValidationError(f"Some products not found: {missing_ids}")

            # Create job status
            job_status = CRUD.create(JobStatus, {
                'store_id': store_id,
                'job_type': 'generate',
                'prompt_type': prompt_type,
                'status': 'pending',
                'total_records': len(record_ids)
            })
            CRUD.db_commit()

            # Start background task
            generate_content_task.delay(store_id, user_id, record_ids, prompt_type, job_status.id)

            return {
                'message': 'Content generation started',
                'job_id': job_status.id,
                'status': job_status.to_dict()
            }, 202

        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'store_id': store_id,
                'record_ids': record_ids
            })
            return {'error': str(e)}, 400

        except ResourceNotFoundError as e:
            current_app.logger.warning(f"Resource not found: {str(e)}", extra={
                'store_id': store_id
            })
            return {'error': str(e)}, 404

        except JobInProgressError as e:
            current_app.logger.info(f"Job in progress: {str(e)}", extra={
                'store_id': store_id,
                'existing_job_id': existing_job.id if existing_job else None
            })
            return {
                'message': str(e),
                'job_id': existing_job.id,
                'status': existing_job.to_dict()
            }, 409

        except Exception as e:
            current_app.logger.error(f"Failed to start generation: {str(e)}", extra={
                'store_id': store_id,
                'error_type': type(e).__name__,
                'error_details': str(e)
            })
            CRUD.db_rollback()
            return {'error': 'An unexpected error occurred'}, 500

    @staticmethod
    def get_job_status(store_id: int, job_id: int) -> Tuple[Dict[str, Any], int]:
        """Get the status of a generation or sync job"""
        try:
            job_status = JobStatus.query.filter_by(
                store_id=store_id,
                id=job_id
            ).first()

            if not job_status:
                return {'error': 'Job not found'}, 404

            return {
                'status': job_status.to_dict(),
                'details': {
                    'processed': job_status.processed_records,
                    'total': job_status.total_records,
                    'success': job_status.success_count,
                    'errors': job_status.error_count,
                    'progress_percentage': round((job_status.processed_records / job_status.total_records * 100), 2)
                }
            }, 200

        except Exception as e:
            return {'error': str(e)}, 500

    @staticmethod
    def sync_all_generated_records(store_id: int, user_id: int, prompt_type: str) -> Tuple[Dict[str, Any], int]:
        try:
            # Check for existing job
            existing_job = JobStatus.query.filter_by(
                store_id=store_id,
                job_type='sync',
                prompt_type=prompt_type,
                status='in_progress'
            ).first()

            if existing_job:
                raise JobInProgressError("Sync already in progress")

            # Get total count
            total_products = Product.query.filter(
                Product.store_id == store_id,
                Product.generated_content.isnot(None)
            ).count()

            if total_products == 0:
                raise ValidationError(f"No generated content found for prompt type: {prompt_type}")

            # Create job status using CRUD
            job_status = CRUD.create(JobStatus, {
                'store_id': store_id,
                'job_type': 'sync',
                'prompt_type': prompt_type,
                'status': 'pending',
                'total_records': total_products,
                'created_at': datetime.utcnow()
            })

            # Start background task
            sync_all_content_task.delay(store_id, user_id, prompt_type, job_status.id)

            return {
                'message': 'Sync process started',
                'job_id': job_status.id,
                'status': job_status.to_dict()
            }, 202

        except JobInProgressError as e:
            current_app.logger.info(f"Job in progress: {str(e)}", extra={
                'store_id': store_id,
                'existing_job_id': existing_job.id if existing_job else None
            })
            return {
                'message': str(e),
                'job_id': existing_job.id,
                'status': existing_job.to_dict()
            }, 409
        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'store_id': store_id,
                'prompt_type': prompt_type
            })
            return {'error': str(e)}, 400
        except Exception as e:
            current_app.logger.error(f"Failed to start sync: {str(e)}", extra={
                'store_id': store_id,
                'error_type': type(e).__name__
            })
            return {'error': 'An unexpected error occurred'}, 500

    @staticmethod
    def update_and_deploy_content(store_id: int, user_id: int, product_id: int, content_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Update and optionally deploy the generated content for a product.

        Parameters:
            store_id: ID of the store
            user_id: ID of the store owner
            product_id: ID of the product to update
            content_data: Dict containing:
                - edited_content: Updated content
                - prompt_type: Type of content (seo_description, meta_title)
                - deploy: Boolean indicating whether to deploy to Shopify
                - deployment_fields: List of fields to deploy (description, meta_title, etc.)

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success/error message and updated content
                status_code: 200 for success, 404/400 for errors
        """
        try:
            # Validate input
            required_fields = ['edited_content', 'prompt_type']
            missing_fields = [field for field in required_fields if field not in content_data]
            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Get store and validate
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                raise ResourceNotFoundError("Store not found")

            # Get product and validate
            product = Product.query.filter_by(id=product_id, store_id=store_id).first()
            if not product:
                raise ResourceNotFoundError("Product not found")

            # Update the content in our database
            update_data = {
                'edited_content': content_data['edited_content'],
                'last_edited_at': datetime.utcnow(),
                'edited_by_user_id': user_id
            }

            CRUD.update(Product, {'id': product_id}, update_data)
            CRUD.db_commit()

            response_data = {
                'message': 'Content updated successfully',
                'product_id': product_id,
                'content': content_data['edited_content']
            }

            # Handle deployment if requested
            if content_data.get('deploy', False):
                try:
                    # Initialize Shopify client
                    shopify_session = PromptService._get_shopify_client(store)
                    with shopify_session:
                        # Get Shopify product
                        shopify_product = shopify.Product.find(product.shopify_product_id)
                        
                        # Prepare deployment data
                        deployment_fields = content_data.get('deployment_fields', ['description'])
                        update_fields = {}
                        
                        if 'description' in deployment_fields:
                            update_fields['body_html'] = content_data['edited_content']
                        if 'meta_title' in deployment_fields:
                            update_fields['metafields'] = [{
                                'namespace': 'global',
                                'key': 'title_tag',
                                'value': content_data['edited_content'],
                                'type': 'single_line_text_field'
                            }]
                        
                        # Update Shopify product
                        for field, value in update_fields.items():
                            setattr(shopify_product, field, value)
                        
                        if shopify_product.save():
                            # Update sync status
                            CRUD.update(Product, {'id': product_id}, {
                                'sync_status': 'synced',
                                'last_synced_at': datetime.utcnow()
                            })
                            CRUD.db_commit()
                            
                            response_data['deployment'] = {
                                'status': 'success',
                                'fields_updated': deployment_fields
                            }
                        else:
                            raise APIError("Failed to save product to Shopify")

                except Exception as e:
                    current_app.logger.error(f"Deployment failed: {str(e)}", extra={
                        'store_id': store_id,
                        'product_id': product_id,
                        'error': str(e)
                    })
                    response_data['deployment'] = {
                        'status': 'failed',
                        'error': str(e)
                    }
                    # Note: We don't raise here as the content update was successful

            return response_data, 200

        except ValidationError as e:
            current_app.logger.warning(f"Validation error: {str(e)}", extra={
                'store_id': store_id,
                'product_id': product_id,
                'content_data': content_data
            })
            return {'error': str(e)}, 400

        except ResourceNotFoundError as e:
            current_app.logger.warning(f"Resource not found: {str(e)}", extra={
                'store_id': store_id,
                'product_id': product_id
            })
            return {'error': str(e)}, 404

        except Exception as e:
            current_app.logger.error(f"Failed to update content: {str(e)}", extra={
                'store_id': store_id,
                'product_id': product_id,
                'error_type': type(e).__name__
            })
            CRUD.db_rollback()
            return {'error': 'An unexpected error occurred'}, 500

@shared_task
def generate_content_task(store_id: int, user_id: int, record_ids: List[int], prompt_type: str, job_id: int):
    try:
        current_app.logger.info(f"Starting content generation for job {job_id}")
        
        job_status = JobStatus.query.get(job_id)
        if not job_status:
            raise ResourceNotFoundError(f"Job status not found with ID: {job_id}")

        store = Store.query.get(store_id)
        if not store:
            raise ResourceNotFoundError(f"Store not found with ID: {store_id}")

        # Update job status using CRUD
        CRUD.update(JobStatus, {'id': job_id}, {
            'status': 'in_progress',
            'updated_at': datetime.utcnow()
        })
        CRUD.db_commit()

        records = Product.query.filter(
            Product.store_id == store_id,
            Product.id.in_(record_ids)
        ).all()

        for i, record in enumerate(records):
            try:
                generated_content = PromptService._generate_prompt_content(
                    record=record,
                    prompt_type=prompt_type,
                    store=store
                )
                
                # Update product using CRUD
                CRUD.update(Product, {'id': record.id}, {
                    'generated_content': generated_content,
                    'updated_at': datetime.utcnow()
                })
                
                # Update job status using CRUD
                CRUD.update(JobStatus, {'id': job_id}, {
                    'processed_records': i + 1,
                    'success_count': job_status.success_count + 1,
                    'updated_at': datetime.utcnow()
                })
                CRUD.db_commit()

            except Exception as e:
                error_details = {
                    'record_id': record.id,
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
                current_app.logger.error(f"Error processing record: {str(e)}", extra=error_details)
                
                # Update error count using CRUD
                CRUD.update(JobStatus, {'id': job_id}, {
                    'error_count': job_status.error_count + 1,
                    'errors': job_status.errors + [error_details],
                    'updated_at': datetime.utcnow()
                })
                CRUD.db_commit()

        # Mark job as completed using CRUD
        CRUD.update(JobStatus, {'id': job_id}, {
            'status': 'completed',
            'updated_at': datetime.utcnow()
        })
        CRUD.db_commit()

    except ResourceNotFoundError as e:
        current_app.logger.error(f"Resource not found: {str(e)}", extra={
            'job_id': job_id,
            'store_id': store_id
        })
        if job_status:
            CRUD.update(JobStatus, {'id': job_id}, {
                'status': 'failed',
                'errors': job_status.errors + [{
                    'error_type': 'RESOURCE_NOT_FOUND',
                    'error_message': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }],
                'updated_at': datetime.utcnow()
            })
            CRUD.db_commit()
    except Exception as e:
        current_app.logger.error(f"Background task failed: {str(e)}", extra={
            'job_id': job_id,
            'error_type': type(e).__name__
        })
        if job_status:
            CRUD.update(JobStatus, {'id': job_id}, {
                'status': 'failed',
                'errors': job_status.errors + [{
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }],
                'updated_at': datetime.utcnow()
            })
            CRUD.db_commit()

    @staticmethod
    def _generate_prompt_content(record: Product, prompt_type: str, store: Store = None) -> str:
        """
        Generate content based on prompt type using the store's preferences and templates.
        Uses Google's Gemini API for content generation.
        """
        try:
            if not store:
                store = Store.query.get(record.store_id)
            
            if not store:
                error_msg = f"No store found for product {record.id}"
                current_app.logger.error(error_msg, extra={
                    'product_id': record.id,
                    'product_title': record.title
                })
                raise ValueError(error_msg)

            # API initialization logging
            current_app.logger.info("Initializing Gemini API")
            
            # Content generation logging
            current_app.logger.info(
                f"Generating content for product {record.id}",
                extra={
                    'product_title': record.title,
                    'product_type': record.product_type
                }
            )

            try:
                genai.configure(api_key=current_app.config['GEMINI_API_KEY'])
                model = GenerativeModel('gemini-pro')
            except Exception as e:
                current_app.logger.error(
                    "Failed to initialize Gemini API",
                    extra={
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                )
                raise

            # Prepare context for template rendering
            context = {
                'product_title': record.title,
                'original_description': record.description,
                'product_type': record.product_type,
                'vendor': record.vendor,
                'price': str(record.price),
                'tags': record.tags,
                'variants': [
                    {
                        'title': v.title,
                        'price': str(v.price),
                        'sku': v.sku,
                        'inventory_quantity': v.inventory_quantity
                    } for v in record.variants
                ] if record.variants else [],
                'images': [img.src for img in record.images] if record.images else [],
                'tone': store.prompt_preferences.get('tone', 'professional'),
                'target_audience': store.prompt_preferences.get('target_audience', 'general'),
                'writing_style': store.prompt_preferences.get('writing_style', 'descriptive'),
                'brand_voice': store.prompt_preferences.get('brand_voice', {})
            }

            # Prepare the system context and prompt
            system_context = f"""
            You are a professional product content writer with expertise in {store.prompt_preferences.get('industry', 'e-commerce')}.
            Follow these guidelines:
            - Tone: {context['tone']}
            - Target Audience: {context['target_audience']}
            - Writing Style: {context['writing_style']}
            - Brand Voice: {context['brand_voice']}
            """

            # Prepare the prompt based on type
            if prompt_type == 'seo_description':
                content_prompt = f"""
                {system_context}

                Create an SEO-optimized product description for:
                Product: {context['product_title']}
                Type: {context['product_type']}
                Original Description: {context['original_description']}
                Key Features: {', '.join(store.prompt_preferences.get('key_features', []))}
                Must Include: {', '.join(store.prompt_preferences.get('must_include_elements', []))}
                Avoid Words: {', '.join(store.prompt_preferences.get('avoid_words', []))}
                """
            elif prompt_type == 'meta_title':
                content_prompt = f"""
                {system_context}

                Create an SEO-optimized meta title for:
                Product: {context['product_title']}
                Type: {context['product_type']}
                Key Features: {', '.join(store.prompt_preferences.get('key_features', []))}
                """
            else:
                content_prompt = f"{system_context}\n\n{prompt.template.format(**context)}"

            # Call Gemini API
            response = model.generate_content(
                content_prompt,
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 500,
                    'top_p': 0.8,
                    'top_k': 40
                }
            )

            generated_content = response.text.strip()

            # Post-process the content
            processed_content = PromptService._post_process_content(
                content=generated_content,
                preferences=store.prompt_preferences,
                prompt_type=prompt_type
            )

            return processed_content

        except Exception as e:
            error_details = {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'product_id': record.id,
                'product_title': record.title,
                'store_id': store.id if store else None,
                'prompt_type': prompt_type,
                'timestamp': datetime.utcnow().isoformat()
            }
            current_app.logger.error(
                f"Error generating prompt content: {str(e)}",
                extra=error_details
            )
            raise

    @staticmethod
    def _sync_to_shopify(store: Store, record: Product, prompt_type: str):
        try:
            current_app.logger.info(f"Starting Shopify sync for product {record.id}")
            
            # Update sync status
            record.update_sync_status(
                prompt_type=prompt_type,
                synced=True,
                synced_at=datetime.utcnow()
            )
            
        except Exception as e:
            current_app.logger.error(
                "Shopify sync failed",
                extra={
                    'product_id': record.id,
                    'error': str(e)
                }
            )

    @staticmethod
    def _get_shopify_client(store: Store) -> shopify.Session:
        """
        Get a Shopify client for the given store.

        Parameters:
            store: Store object containing Shopify credentials

        Returns:
            shopify.Session: Initialized Shopify client
        """
        return shopify.Session(
            shop_url=store.shop_url,
            version=current_app.config['SHOPIFY_API_VERSION'],
            access_token=store.access_token
        ) 