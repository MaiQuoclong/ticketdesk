from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Phân trang chuẩn cho REST API hỗ trợ tham số page và page_size."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
