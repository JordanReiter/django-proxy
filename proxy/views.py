try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

import requests
from django.http import HttpResponse
from django.http import QueryDict
from django.conf import settings
from django.core.urlresolvers import reverse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .utils import proxy_reverse, rewrite_response

IGNORE_SSL = getattr(settings, 'PROXY_IGNORE_SSL', False)

@csrf_exempt
def proxy_view(request, url, domain=None, secure=False, requests_args=None, template_name="proxy/debug.html"):
    """
    Forward as close to an exact copy of the request as possible along to the
    given url.  Respond with as close to an exact copy of the resulting
    response as possible.

    If there are any additional arguments you wish to send to requests, put
    them in the requests_args dictionary.
    """
    requests_args = (requests_args or {}).copy()
    headers = get_headers(request.META)
    params = request.GET.copy()

    proxy_domain = settings.PROXY_DOMAIN

    protocol = 'http'
    if secure:
        protocol = 'https'

    url = '%s://%s/%s' % (protocol, proxy_domain, url[1:] if url.startswith('/') else url)


    if 'headers' not in requests_args:
        requests_args['headers'] = {}
    if 'data' not in requests_args:
        requests_args['data'] = request.body
    if 'params' not in requests_args:
        requests_args['params'] = QueryDict('', mutable=True)
    if 'cookies' not in requests_args and getattr(settings, 'PROXY_SET_COOKIES', False):
        headers = dict([ (kk, vv) for kk, vv in headers.items() if kk.lower() != 'cookie' ])
        requests_args['cookies'] = get_cookies(request, proxy_domain)

    # Overwrite any headers and params from the incoming request with explicitly
    # specified values for the requests library.
    headers.update(requests_args['headers'])
    params.update(requests_args['params'])

    # If there's a content-length header from Django, it's probably in all-caps
    # and requests might not notice it, so just remove it.
    for key in headers.keys():
        if key.lower() == 'content-length':
            del headers[key]

    requests_args['headers'] = headers
    requests_args['params'] = params

    if settings.DEBUG and request.method != 'HEAD':
        requests_args['allow_redirects'] = False


    response = requests.request(request.method, url, **requests_args)

    if getattr(settings, 'PROXY_SET_COOKIES', False):
        set_cookies(request, proxy_domain, response.cookies)

    content_type = response.headers['content-type']
    content = response.content
    show_debug = False
    if 'html' in content_type.lower():
        content = rewrite_response(content, proxy_domain, secure=secure or IGNORE_SSL)
        show_debug = settings.DEBUG
    elif 'javascript' in content_type.lower():
        content = rewrite_script(content, proxy_domain, secure=secure or IGNORE_SSL)

    if show_debug:
        ctx = {
            'url': url,
            'requests_args': requests_args,
            'response': content,
            'headers': response.headers,
            'status': response.status_code,
        }
        if int(response.status_code) in (301, 302):
            redirection = response.headers['location']
            if proxy_domain in urljoin('http://%s' % proxy_domain, redirection):
                redirection = proxy_reverse(redirection, secure)
            ctx['redirection'] = redirection
        proxy_response = render(request, template_name, ctx)
    else:
        proxy_response = HttpResponse(
            content,
            status=response.status_code)


    excluded_headers = set([
        # Hop-by-hop headers
        # ------------------
        # Certain response headers should NOT be just tunneled through.  These
        # are they.  For more info, see:
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.5.1
        'connection', 'keep-alive', 'proxy-authenticate', 
        'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 
        'upgrade', 

        # Although content-encoding is not listed among the hop-by-hop headers,
        # it can cause trouble as well.  Just let the server set the value as
        # it should be.
        'content-encoding',

        # Since the remote server may or may not have sent the content in the
        # same encoding as Django will, let Django worry about what the length
        # should be.
        'content-length',
    ])
    for key, value in response.headers.items():
        if key.lower() in excluded_headers:
            continue
        proxy_response[key] = value


    return proxy_response


PROXY_COOKIE_SESSION_KEY = '__proxy_cookiefile_%s'

def get_session_key(domain):
    return PROXY_COOKIE_SESSION_KEY % domain.replace('.', '_')

def get_cookies(request, domain):
    return request.session.get(get_session_key(domain))

def set_cookies(request, domain, cookies):
    try:
        jar = request.session[get_session_key(domain)]
    except KeyError:
        jar = requests.cookies.RequestsCookieJar()
    try:
        for cookie in cookies:
            jar.set_cookie(cookie)
    except AttributeError:
        for key, value in cookies.items():
            cookie = SimpleCookie()
            cookie[key] = value
            jar.set_cookie(cookie)
    request.session[get_session_key(domain)] = jar
    request.session.modified = True

def get_headers(environ):
    """
    Retrieve the HTTP headers from a WSGI environment dictionary.  See
    https://docs.djangoproject.com/en/dev/ref/request-response/#django.http.HttpRequest.META
    """
    headers = {}
    for key, value in environ.items():
        # Sometimes, things don't like when you send the requesting host through.
        if key.startswith('HTTP_') and key != 'HTTP_HOST':
            headers[key[5:].replace('_', '-')] = value
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            headers[key.replace('_', '-')] = value

    return headers
