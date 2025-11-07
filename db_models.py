from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from datetime import datetime

db = SQLAlchemy()

class HTRResult(db.Model):
    __tablename__ = 'htr_extracted_data'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.String(128), nullable=False)
    source_type = db.Column(db.String(32), nullable=False)  # 'MANDATE_CARD' or 'NATIONAL_ID'
    field_name = db.Column(db.String(64), nullable=False)
    extracted_value = db.Column(db.Text)
    confidence_score = db.Column(db.Float, default=0.99)
    is_corrected = db.Column(db.Boolean, default=False)
    corrected_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('document_id', 'source_type', 'field_name', name='uq_doc_source_field'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "source_type": self.source_type,
            "field_name": self.field_name,
            "extracted_value": self.extracted_value,
            "confidence_score": self.confidence_score,
            "is_corrected": self.is_corrected,
            "corrected_value": self.corrected_value,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
