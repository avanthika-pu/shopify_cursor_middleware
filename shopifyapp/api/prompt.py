from flask import Blueprint, jsonify, request
from shopifyapp.services.prompt_service import PromptService
from shopifyapp.api.auth import token_required

prompt_bp = Blueprint('prompt', __name__)

@prompt_bp.route('/stores/<int:store_id>/prompts/preferences', methods=['GET'])
@token_required
def get_prompt_preferences(current_user, store_id):
    """Get prompt preferences for a store"""
    result, status_code = PromptService.get_prompt_preferences(
        store_id=store_id,
        user_id=current_user.id
    )
    return jsonify(result), status_code

@prompt_bp.route('/stores/<int:store_id>/prompts/preferences', methods=['PUT'])
@token_required
def update_prompt_preferences(current_user, store_id):
    """Update prompt preferences for a store"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    result, status_code = PromptService.update_prompt_preferences(
        store_id=store_id,
        user_id=current_user.id,
        preferences=data
    )
    return jsonify(result), status_code

@prompt_bp.route('/prompts/options', methods=['GET'])
@token_required
def get_available_options():
    """Get available options for prompt preferences"""
    return jsonify(PromptService.get_available_options()), 200

@prompt_bp.route('/stores/<int:store_id>/prompts/generate', methods=['POST'])
@token_required
def generate_selective_prompts(current_user, store_id):
    """Generate prompts for selected records"""
    data = request.get_json()
    if not data or 'record_ids' not in data:
        return jsonify({'error': 'No record IDs provided'}), 400

    result, status_code = PromptService.generate_selective_prompts(
        store_id=store_id,
        user_id=current_user.id,
        record_ids=data['record_ids'],
        prompt_type=data.get('prompt_type', 'seo_description')  # default to seo_description
    )
    return jsonify(result), status_code

@prompt_bp.route('/stores/<int:store_id>/prompts/sync', methods=['POST'])
@token_required
def sync_selective_records(current_user, store_id):
    """Sync generated prompts for selected records"""
    data = request.get_json()
    if not data or 'record_ids' not in data:
        return jsonify({'error': 'No record IDs provided'}), 400

    result, status_code = PromptService.sync_selective_records(
        store_id=store_id,
        user_id=current_user.id,
        record_ids=data['record_ids'],
        prompt_type=data.get('prompt_type', 'seo_description')
    )
    return jsonify(result), status_code

@prompt_bp.route('/stores/<int:store_id>/prompts/sync-all', methods=['POST'])
@token_required
def sync_all_generated_records(current_user, store_id):
    """Sync all generated content to Shopify"""
    data = request.get_json()
    if not data or 'prompt_type' not in data:
        return jsonify({'error': 'prompt_type is required'}), 400

    result, status_code = PromptService.sync_all_generated_records(
        store_id=store_id,
        user_id=current_user.id,
        prompt_type=data['prompt_type']
    )
    return jsonify(result), status_code

@prompt_bp.route('/stores/<int:store_id>/prompts/jobs/<int:job_id>', methods=['GET'])
@token_required
def get_job_status(current_user, store_id, job_id):
    """Get status of a generation or sync job"""
    result, status_code = PromptService.get_job_status(store_id, job_id)
    return jsonify(result), status_code

@prompt_bp.route('/stores/<int:store_id>/products/<int:product_id>/content', methods=['PUT'])
@token_required
def update_and_deploy_content(current_user, store_id, product_id):
    """Update and optionally deploy generated content"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    result, status_code = PromptService.update_and_deploy_content(
        store_id=store_id,
        user_id=current_user.id,
        product_id=product_id,
        content_data=data
    )
    return jsonify(result), status_code 