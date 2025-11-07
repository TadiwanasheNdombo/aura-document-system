from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class DocumentExtraction(db.Model):
    __tablename__ = 'document_extractions'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.String(128), nullable=False, unique=True)
    surname = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    occupation = db.Column(db.String(128), nullable=False)
    gross_monthly_income = db.Column(db.Float, nullable=False)
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Ground truth fields for human correction
    gt_surname = db.Column(db.String(128))
    gt_name = db.Column(db.String(128))
    gt_occupation = db.Column(db.String(128))
    gt_gross_monthly_income = db.Column(db.Float)
    gt_updated_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "document_id": self.document_id,
            "surname": self.surname,
            "name": self.name,
            "occupation": self.occupation,
            "gross_monthly_income": self.gross_monthly_income,
            "gt_surname": self.gt_surname,
            "gt_name": self.gt_name,
            "gt_occupation": self.gt_occupation,
            "gt_gross_monthly_income": self.gt_gross_monthly_income,
            "extracted_at": self.extracted_at,
            "gt_updated_at": self.gt_updated_at
        }
