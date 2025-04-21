from datetime import datetime
from shopifyapp.models.user import db

class JobStatus(db.Model):
    __tablename__ = 'job_status'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    job_type = db.Column(db.String(50), nullable=False)  # 'generate' or 'sync'
    prompt_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'pending', 'in_progress', 'completed', 'failed'
    total_records = db.Column(db.Integer, nullable=False)
    processed_records = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    record_ids = db.Column(db.JSON)  # Store the record IDs being processed
    errors = db.Column(db.JSON, default=[])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'job_type': self.job_type,
            'prompt_type': self.prompt_type,
            'status': self.status,
            'total_records': self.total_records,
            'processed_records': self.processed_records,
            'progress_percentage': round((self.processed_records / self.total_records * 100), 2) if self.total_records > 0 else 0,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        } 