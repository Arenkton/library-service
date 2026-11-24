from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CustomJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = (
        "rest_framework_simplejwt.authentication.JWTAuthentication"
    )
    name = "JWTAuth"
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorize",
            "description": "Enter: Bearer <access_token>",
        }
