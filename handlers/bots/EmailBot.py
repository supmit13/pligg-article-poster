import os, sys, re, time, gzip
import urllib, urllib2, htmllib
from urlparse import urlparse
import httplib
from BeautifulSoup import BeautifulSoup
import StringIO
import shelve # For serialization of objects


class NoRedirectHandler(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        infourl = urllib.addinfourl(fp, headers, req.get_full_url())
        infourl.status = code
        infourl.code = code
        return infourl

    http_error_300 = http_error_302
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302 



"""
Parent class for all Email Bots.
It defines some class methods as well as some instance methods that are generic to all email services.
"""
class EmailBot(object):
    absUrlPattern = re.compile(r"^https?:\/\/", re.IGNORECASE)
    # Set DEBUG to False on prod env
    DEBUG = False
    startUrl = None

    def __init__(self, username="", passwd=""):
        self.opener = urllib2.build_opener() # This is my normal opener....
        self.no_redirect_opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler(), NoRedirectHandler()) # ... and this the "abnormal" one.
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.10) Gecko/20111103 Firefox/3.6.24',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.homeDir = os.getcwd()
        self.requestUrl = self.__class__.startUrl
        parsedUrl = urlparse(self.requestUrl)
        self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/"
        # First, get the Service login page.
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        self.pageResponse = None
        self.requestMethod = "GET"
        self.postData = {}
        self.currentPageContent = ""
        self.username = username
        self.password = passwd
        self.isLoggedIn = False
        self.lastChecked = None
        self.currentPageEmailsList = [] # Holds the list of emails listed on the page that is being read.
        self.currentFolder = "" # Holds the folder that is currently being read.
        self.currentPage = -1 # Page number of the page that is currently being read.
        self.maxPageNumberCurrentFolder = 0 # Maximum page number for the folder that is currently being processed.
        
        
    def _getCookieFromResponse(cls, lastHttpResponse):
        cookies = ""
        lastResponseHeaders = lastHttpResponse.info()
        responseCookies = lastHttpResponse.info().getheaders("Set-Cookie")
        pathCommaPattern = re.compile(r"path=/,", re.IGNORECASE)
        domainPattern = re.compile(r"Domain=[^;]+;", re.IGNORECASE)
        expiresPattern = re.compile(r"Expires=[^;]+;", re.IGNORECASE)
        if responseCookies.__len__() > 1:
            for cookie in responseCookies:
                cookieParts = cookie.split("Path=/")
                cookieParts[0] = re.sub(domainPattern, "", cookieParts[0])
                cookieParts[0] = re.sub(expiresPattern, "", cookieParts[0])
                cookies += cookieParts[0]
            return(cookies)
        else:
            if lastResponseHeaders.has_key("Set-Cookie"):
                cookieValue = lastResponseHeaders.get("Set-Cookie")
                cookieLines = cookieValue.split("\r\n")
                if pathCommaPattern.search(cookieValue):
                    cookieLines = cookieValue.split("path=/,")
                deletedPattern = re.compile("deleted", re.IGNORECASE)
                for line in cookieLines:
                    if deletedPattern.search(line):
                        continue
                    cookieParts = line.split(";")
                    cookies += cookieParts[0].__str__() + ";"
                cookies.strip()
                cookies = cookies[:-1]
            return (cookies)
    
    _getCookieFromResponse = classmethod(_getCookieFromResponse)


    def getPageContent(self):
        return(self.pageResponse.read())

    def getChunkedPageContent(self):
        content = ""
        while True:
            partial_content = self.pageResponse.read()
            if partial_content == '\r\n':
                break
            content += partial_content
        return(content)
    
        
    def _decodeGzippedContent(cls, encoded_content):
        response_stream = StringIO.StringIO(encoded_content)
        decoded_content = ""
        try:
            gzipper = gzip.GzipFile(fileobj=response_stream)
            decoded_content = gzipper.read()
        except: # Maybe this isn't gzipped content after all....
            decoded_content = encoded_content
        return(decoded_content)

    _decodeGzippedContent = classmethod(_decodeGzippedContent)

    """
    Retrieves the base URL of the page whose content is being passed as the 2nd argument. The base URL for
    the page is expected to be specified with a '<base href="...">' tag.
    """
    def _getPageBaseURL(cls, pageContent):
        soup = BeautifulSoup(pageContent)
        pageBaseTag = soup.find("base")
        pageBaseUrl = ""
        if pageBaseTag and pageBaseTag.has_key("href"):
            pageBaseUrl = pageBaseTag.get("href")
        return (pageBaseUrl)
    _getPageBaseURL = classmethod(_getPageBaseURL)



    def doLogin(self, username="", password=""):
        pass


    def _getJavascriptCookies(self, html):
        pass
        
    def getLastRequestUrl(self):
        return(self.requestUrl)


    """
    Class method to identify if a URL (passed to this method) is a relative URL or an absolute one.
    """
    def _isAbsoluteUrl(cls, url):
        s = cls.absUrlPattern.search(url)
        if s:
            return True
        else:
            return False
    _isAbsoluteUrl = classmethod(_isAbsoluteUrl)

    def _getPathToPage(cls, url):
        urlParts = url.split("?")
        urlPartsList = urlParts[0].split("/")
        urlPartsList.pop()
        urlPath = "/".join(urlPartsList)
        return urlPath
    _getPathToPage = classmethod(_getPathToPage)

    def serializeSessionInfo(self, filename):
        pass


    def loadSerializedSessionInfo(self, filename):
        pass


    """
    Handle all illegal and undefined attribute accesses gracefully.
    """
    def __getattr__(self, attrname):
        if attrname not in self.__dict__.keys():
            print "'%s' is not defined as yet. You may extend the class you are using and add the attribute if you want to use it."%attrname
        else:
            pass



"""
The following class defines an 'EmailMessage' object. 
"""
class EmailMessage(object):
    pass



if __name__ == "__main__":
    pass

# supmit

