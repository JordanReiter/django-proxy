from django.conf.urls import url

from .views import proxy_view

urlpatterns = [
    url(r'^_s/(?P<url>.*)$', proxy_view, {'secure': True }, name='proxy_secure'),
    url(r'^(?P<url>.*)$', proxy_view, name='proxy'),
]
