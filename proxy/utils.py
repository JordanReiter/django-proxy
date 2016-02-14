import re
import urllib2
import urlparse

from bs4 import BeautifulSoup

def proxy_reverse(url, secure=False):
    from django.core.urlresolvers import reverse
    print "Rendering reverse proxy url for ", url
    secure = (
        (secure or url.startswith('https://')) and 
        not url.startswith('http://')
    )
    parsed_url = urlparse.urlparse(url)
    #print parsed_url
    new_uri = "%s%s%s" % ( 
        parsed_url.path, 
        "?" + parsed_url.query if parsed_url.query else "", 
        "#" + parsed_url.fragment if parsed_url.fragment else ""
    )
    if new_uri and new_uri[0] == '/':
        new_uri = new_uri[1:]
    process_view_name = 'proxy'
    #print "New uri is ", new_uri
    if secure:
        process_view_name = 'proxy_secure'
    reversed_url = reverse(process_view_name, args=[new_uri])
    print "Reversed URL is", reversed_url
    return reversed_url


def rewrite_url(tag, domain, attr='href', secure=False):
    #print "Looking at", tag, domain
    old_url = tag.get(attr)
    if not old_url:
        return
    if not re.search(r'^(?:https?:/)?/', old_url): # local, query, or hash
        print "Skipping", old_url
        return
    secure = (
        (secure or old_url.startswith('https://')) and 
        not old_url.startswith('http://')
    )
    #print old_url, " is secure? ", secure
    if not secure and not re.search(r'^(?:https?)?://', old_url):
        return
    #print old_url, re.search(r'^(?:https?)?://', old_url)
    protocol = 'http'
    if secure:
        protocol = 'https'
    new_url = urlparse.urljoin('%s://%s' % (protocol, domain), old_url)
    #print "New url is ", new_url
    if domain in new_url:
        tag[attr] = proxy_reverse(new_url, secure)


LOCAL_URL_REGEX = r"""(?:https?:)//(?:www\.)?%s[^"'\s]*"""
def rewrite_script(script_content, domain, secure=False):
    new_content = script_content
    pos = 0
    match = re.search(LOCAL_URL_REGEX % domain, script_content)
    while match:
        old_url = script_content[match.start():match.end()]
        new_url = re.sub(LOCAL_URL_REGEX % domain, r"", old_url)
        script_content = "".join([script_content[:match.start()], proxy_reverse(new_url, secure), script_content[match.end():]])
        pos = match.end()
        match = re.search(LOCAL_URL_REGEX % domain, script_content)
    return script_content


def rewrite_response(resp, domain=None, secure=False):
    soup = BeautifulSoup(resp, "html5lib")
    for anchor_tag in soup.findAll('a'):
        rewrite_url(anchor_tag, domain, secure=secure)

    for link_tag in soup.findAll('link'):
        rewrite_url(link_tag, domain, secure=secure)

    for script_tag in soup.findAll('script'):
        if script_tag.get('src'):
            rewrite_url(script_tag, domain, attr='src', secure=secure)
        else:
            script_tag.string = rewrite_script(script_tag.string, domain, secure)

    for img_tag in soup.findAll('img'):
        rewrite_url(img_tag, domain, attr='src', secure=secure)

    for form_tag in soup.findAll('form'):
        rewrite_url(form_tag, domain, attr='action', secure=secure)

    return unicode(soup)

