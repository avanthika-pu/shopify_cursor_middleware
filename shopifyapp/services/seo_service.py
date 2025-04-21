from flask import current_app
import google.generativeai as genai
from shopifyapp.models.store import Store
from shopifyapp.models.product import Product
from shopifyapp.models.prompt import Prompt
from shopifyapp.models.user import db
from shopifyapp.services.prompt_service import PromptService
from datetime import datetime
import os

class SEOService:
    @staticmethod
    def _get_optimized_description(original_description: str, product_title: str,
                                 store_preferences: dict = None, store_id: int = None) -> str:
        """
        Generate an optimized product description using Gemini AI.

        Parameters:
            original_description: Original product description text
            product_title: Title of the product
            store_preferences: Store's prompt preferences and settings
            store_id: ID of the store for template lookup

        Returns:
            HTML formatted optimized description

        Raises:
            Exception: If AI generation or template rendering fails
        """
        try:
            # Configure Gemini AI
            genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
            model = genai.GenerativeModel('gemini-pro')
            
            # Get active prompt template
            prompt = Prompt.query.filter_by(store_id=store_id, is_active=True).first()
            if not prompt:
                # Create and use default prompt if none exists
                prompt = Prompt.create_default_prompt(store_id)
                db.session.add(prompt)
                db.session.commit()

            # Prepare context for prompt template
            context = {
                'product_title': product_title,
                'original_description': original_description,
                'tone': store_preferences.get('tone', 'professional'),
                'target_audience': store_preferences.get('target_audience', 'general'),
                'writing_style': store_preferences.get('writing_style', 'descriptive'),
                'seo_keywords_focus': store_preferences.get('seo_keywords_focus', 'balanced'),
                'description_length': store_preferences.get('description_length', 'medium'),
                'key_features': store_preferences.get('key_features', []),
                'brand_voice': store_preferences.get('brand_voice', {
                    'personality': 'professional',
                    'emotion': 'neutral',
                    'formality': 'formal'
                }),
                'industry_specific': store_preferences.get('industry_specific', {
                    'industry': None,
                    'specializations': [],
                    'technical_level': 'moderate'
                }),
                'custom_instructions': store_preferences.get('custom_instructions'),
                'avoid_words': store_preferences.get('avoid_words', []),
                'must_include_elements': store_preferences.get('must_include_elements', [])
            }

            # Render prompt template
            try:
                prompt_text = PromptService.render_prompt(prompt, context)
            except Exception as e:
                current_app.logger.error(f"Error rendering prompt template: {str(e)}")
                # Fall back to default template
                prompt = Prompt.create_default_prompt(store_id)
                prompt_text = PromptService.render_prompt(prompt, context)

            # Generate optimized description using Gemini AI
            response = model.generate_content(prompt_text)
            optimized_description = response.text

            # Update prompt usage statistics
            prompt.increment_usage()

            # Ensure HTML formatting
            if not optimized_description.strip().startswith('<'):
                optimized_description = f"<p>{optimized_description}</p>"

            return optimized_description

        except Exception as e:
            current_app.logger.error(f"Error in _get_optimized_description: {str(e)}")
            raise Exception(f"Failed to generate optimized description: {str(e)}")

    @staticmethod
    def optimize_product_description(user_id: int, store_id: int, product_id: int, custom_prompt: dict = None) -> tuple:
        """
        Optimize description for a single product.

        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404

            product = Product.query.filter_by(id=product_id, store_id=store_id).first()
            if not product:
                return {'error': 'Product not found'}, 404

            # Get optimized description
            optimized_description = SEOService._get_optimized_description(
                original_description=product.original_description,
                product_title=product.title,
                store_preferences=store.prompt_preferences,
                store_id=store_id
            )

            # Update product
            product.optimized_description = optimized_description
            product.is_optimized = True
            product.last_optimized = datetime.utcnow()
            db.session.commit()

            return {
                'message': 'Product description optimized successfully',
                'product': product.to_dict()
            }, 200
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in optimize_product_description: {str(e)}")
            return {'error': str(e)}, 500

    @staticmethod
    def optimize_all_products(user_id: int, store_id: int, custom_prompt: dict = None) -> tuple:
        """
        Batch optimize descriptions for all products in a store.

        Parameters:
            user_id: ID of the requesting user
            store_id: ID of the store containing products
            custom_prompt: Optional custom prompt template

        Returns:
            tuple: (response_dict, status_code)
                response_dict: Contains success message, optimized products, and errors
                status_code: 200 for success, 207 for partial success, 404/500 for errors

        Raises:
            Exception: If batch optimization fails
        """
        try:
            store = Store.query.filter_by(id=store_id, user_id=user_id).first()
            if not store:
                return {'error': 'Store not found'}, 404

            products = Product.query.filter_by(store_id=store_id).all()
            optimized_products = []
            errors = []

            for product in products:
                try:
                    # Get optimized description
                    optimized_description = SEOService._get_optimized_description(
                        original_description=product.original_description,
                        product_title=product.title,
                        store_preferences=store.prompt_preferences,
                        store_id=store_id
                    )

                    # Update product
                    product.optimized_description = optimized_description
                    product.is_optimized = True
                    product.last_optimized = datetime.utcnow()
                    optimized_products.append(product.to_dict())

                except Exception as e:
                    current_app.logger.error(f"Error optimizing product {product.id}: {str(e)}")
                    errors.append({
                        'product_id': product.id,
                        'error': str(e)
                    })
                    continue

            db.session.commit()
            
            response = {
                'message': f'Successfully optimized {len(optimized_products)} products',
                'products': optimized_products
            }
            
            if errors:
                response['errors'] = errors
                
            return response, 200 if not errors else 207  # 207 Multi-Status if there are errors
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in optimize_all_products: {str(e)}")
            return {'error': str(e)}, 500 