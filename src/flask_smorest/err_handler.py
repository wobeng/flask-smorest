"""Exception handler"""

from werkzeug.exceptions import HTTPException
from flask import jsonify
import marshmallow as ma


class Error(Exception):
    """
    Error base class more inline with Google JSON guide
    https://google.github.io/styleguide/jsoncstyleguide.xml?showone=error#error
    """

    code = 400
    msg = "Something went wrong"
    error_type = "ApiException"
    reason = ""

    def __init__(
        self,
        message=None,
        code=None,
        errors=None,
        error_type=None,
        reason=None,
    ):
        message = str(message or self.msg)
        super().__init__(message)
        self.errors = errors or []
        self.message = message
        self.error_type = error_type or self.error_type
        self.status_code = code or self.code
        self.reason = reason or self.reason

    def to_dict(self):
        output = {
            "error": {
                "code": self.status_code,
                "message": self.message,
                "error_type": self.error_type,
            }
        }
        if self.reason:
            output["error"]["reason"] = self.reason
        if self.errors:
            output["error"]["errors"] = self.errors
        return output

    def response(self):
        response = jsonify(self.to_dict())
        response.status_code = self.status_code
        return response


class ErrorSchema(ma.Schema):
    """Schema describing the error payload

    Not actually used to dump payload, but only for documentation purposes
    """

    class NestedSchema(ma.Schema):
        code = ma.fields.Integer(metadata={"description": "Error code"})
        message = ma.fields.String(metadata={"description": "Error message"})
        error_type = ma.fields.String(metadata={"description": "Error type"})
        reason = ma.fields.String(metadata={"description": "Reason"})
        errors = ma.fields.List(ma.fields.Dict(metadata={"description": "Errors"}))

    error = ma.fields.Nested(NestedSchema)


class ErrorHandlerMixin:
    """Extend Api to manage error handling."""

    # Should match payload structure in handle_http_exception
    ERROR_SCHEMA = ErrorSchema

    def _register_error_handlers(self):
        """Register error handlers in Flask app

        This method registers a default error handler for ``HTTPException``.
        """
        self._app.register_error_handler(HTTPException, self.handle_http_exception)
        self._app.register_error_handler(Error, self.handle_error_exception)

    @staticmethod
    def convert_webargs_errors(messages):
        """Convert webargs validation error messages to a list of errors

        :param messages: webargs validation error messages
        :type messages: dict
        :return: list of errors
        :rtype: list
        """
        errors = []
        if isinstance(messages, dict):
            for location_type, field_errors in messages.items():
                if isinstance(field_errors, dict):
                    for field, error_messages in field_errors.items():
                        errors.append(
                            {
                                "location": field,
                                "location_type": location_type,
                                "messages": error_messages,
                            }
                        )
        return {
            "code": 400,
            "errors": errors,
            "error_type": "SchemaFieldsException",
            "message": "Request input schema is invalid",
        }

    def handle_error_exception(self, error):
        return error.to_dict(), error.code

    def handle_http_exception(self, error):
        """Return a JSON response containing a description of the error

        This method is registered at app init to handle ``HTTPException``.

        - When ``abort`` is called in the code, an ``HTTPException`` is
          triggered and Flask calls this handler.

        - When an exception is not caught in a view, Flask makes it an
          ``InternalServerError`` and calls this handler.

        flask-smorest republishes webargs's
        :func:`abort <webargs.flaskparser.abort>`. This ``abort`` allows the
        caller to pass kwargs and stores them in ``exception.data`` so that the
        error handler can use them to populate the response payload.

        Extra information expected by this handler:

        - `message` (``str``): a comment
        - `errors` (``dict``): errors, typically validation errors in
            parameters and request body
        - `headers` (``dict``): additional headers
        """
        headers = {}
        payload = {"code": error.code, "error_type": error.name}

        # Get additional info passed as kwargs when calling abort
        # data may not exist if HTTPException was raised without webargs abort
        data = getattr(error, "data", None)
        if data:
            # If we passed a custom message
            if "message" in data:
                payload["message"] = data["message"]
            # If we passed "errors"
            if "errors" in data:
                payload["errors"] = data["errors"]
            # If webargs added validation errors as "messages"
            # (you should use 'errors' as it is more explicit)
            elif "messages" in data:
                payload.update(self.convert_webargs_errors(data["messages"]))
            # If we passed additional headers
            if "headers" in data:
                headers = data["headers"]

        return Error(**payload).to_dict(), payload["code"], headers
