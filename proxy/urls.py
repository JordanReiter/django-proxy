from django.conf.urls import patterns, include, url

urlpatterns = patterns('proxy.views',
    url(r'^_s/(?P<url>.*)$', 'proxy_view', {'secure': True }, name='proxy_secure'),
    url(r'^(?P<url>.*)$', 'proxy_view', name='proxy'),
)
