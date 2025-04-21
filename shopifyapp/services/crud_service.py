from sqlalchemy.exc import IntegrityError

from app import db, logging
from app.services.custom_errors import BadRequest, UnProcessable, NoContent, InternalError


class CRUD:
    @classmethod
    def create(cls, model_cls, data):
        """Create a new record"""
        try:
            record = model_cls(**data)
            db.session.add(record)
            cls.db_commit()
            return record
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"CRUD Create IntegrityError: {model_cls.__name__} {data} {e}")
            if "errors.UniqueViolation" in str(e):
                raise UnProcessable("This data already exists")
            raise UnProcessable("Database integrity error occurred")
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Create Error: {model_cls.__name__} {data} {e}")
            raise BadRequest(f"Failed to create record: {str(e)}")

    @classmethod
    def update(cls, model_cls, condition, data):
        """Update existing record(s)"""
        try:
            record = model_cls.query.filter_by(**condition).update(data)
            if not record:
                raise NoContent()
            cls.db_commit()
            return True
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"CRUD Update IntegrityError: {model_cls.__name__} {condition} {data} {e}")
            if "errors.UniqueViolation" in str(e):
                raise UnProcessable("This data already exists")
            raise UnProcessable("Database integrity error occurred")
        except NoContent:
            raise
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Update Error: {model_cls.__name__} {condition} {data} {e}")
            raise InternalError(f"Failed to update record: {str(e)}")

    @classmethod
    def create_if_not(cls, model_cls, condition, data):
        """Create record if it doesn't exist"""
        try:
            record = model_cls.query.filter_by(**condition).first()
            if not record:
                return cls.create(model_cls, data)
            return record
        except Exception as e:
            logging.error(f"CRUD Create-If-Not Error: {model_cls.__name__} {condition} {data} {e}")
            raise InternalError(f"Failed to create/find record: {str(e)}")

    @classmethod
    def create_or_update(cls, model_cls, condition, data):
        """Create or update record"""
        try:
            record = model_cls.query.filter_by(**condition).first()
            if not record:
                return cls.create(model_cls, data)
            return cls.update(model_cls, condition, data)
        except Exception as e:
            logging.error(f"CRUD Create-Or-Update Error: {model_cls.__name__} {condition} {data} {e}")
            raise InternalError(f"Failed to create/update record: {str(e)}")

    @classmethod
    def bulk_insertion(cls, model_cls, data):
        """Bulk insert records"""
        try:
            objects = [model_cls(**record) for record in data]
            db.session.bulk_save_objects(objects)
            cls.db_commit()
            return True
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"CRUD Bulk Insertion IntegrityError: {model_cls.__name__} {e}")
            raise UnProcessable("Database integrity error during bulk insertion")
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Bulk Insertion Error: {model_cls.__name__} {e}")
            raise InternalError("Bulk insertion failed")

    @classmethod
    def delete(cls, model_cls, condition):
        """Delete record(s)"""
        try:
            records = model_cls.query.filter_by(**condition).all()
            if not records:
                raise NoContent()
            for record in records:
                db.session.delete(record)
            cls.db_commit()
            return True
        except NoContent:
            raise
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Delete Error: {model_cls.__name__} {condition} {e}")
            raise InternalError(f"Failed to delete record(s): {str(e)}")

    @staticmethod
    def db_commit():
        """Safely commit database changes"""
        try:
            db.session.commit()
            return True
        except IntegrityError as e:
            db.session.rollback()
            if "errors.UniqueViolation" in str(e):
                msg = (str(e).split("Key (")[1].split(")")[0].replace("_", " ").title() + " already exists")
            else:
                msg = 'Database integrity error occurred'
            logging.error(f"CRUD Commit IntegrityError: {e}")
            raise InternalError(msg)
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Commit Error: {e}")
            raise InternalError('Unexpected database error occurred')

    @staticmethod
    def transaction_flush():
        """Safely flush database changes"""
        try:
            db.session.flush()
            return True
        except IntegrityError as e:
            db.session.rollback()
            if "errors.UniqueViolation" in str(e):
                msg = (str(e).split("Key (")[1].split(")")[0].replace("_", " ").title() + " already exists")
            else:
                msg = 'Database integrity error occurred'
            logging.error(f"CRUD Flush IntegrityError: {e}")
            raise InternalError(msg)
        except Exception as e:
            db.session.rollback()
            logging.error(f"CRUD Flush Error: {e}")
            raise InternalError('Unexpected database error occurred')
