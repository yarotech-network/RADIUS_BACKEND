from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["count", "total_pages", "current_page", "results"],
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "total_pages": {"type": "integer", "minimum": 1},
                "current_page": {"type": "integer", "minimum": 1},
                "results": schema,
            },
        }

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "current_page": self.page.number,
            "results": data,
        })
