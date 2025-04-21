class ShopifyAppException(Exception):
    """Base exception for the application"""
    pass

class DatabaseOperationError(ShopifyAppException):
    """Database operation failed"""
    pass

class ValidationError(ShopifyAppException):
    """Validation failed"""
    pass

class ResourceNotFoundError(ShopifyAppException):
    """Resource not found"""
    pass

class DuplicateResourceError(ShopifyAppException):
    """Resource already exists"""
    pass

class APIError(ShopifyAppException):
    """External API error"""
    pass

class JobInProgressError(ShopifyAppException):
    """Job already in progress"""
    pass 