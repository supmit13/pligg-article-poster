import os, sys, re, time
import urllib, urllib2, httplib
from BeautifulSoup import BeautifulSoup
import MySQLdb
from ConfigParser import ConfigParser
from bots.EmailBot import NoRedirectHandler, EmailBot
from bots.GmailBot import GmailBot
from bots.YahooMailBot import YahooMailBot
from urlparse import urlparse, urlsplit
import PIL
from contents import ContentSpinner
from StringIO import StringIO
import mimetypes, mimetools

"""
Some utility function definitions
"""
def urlEncodeString(s):
    tmphash = {'str' : s }
    encodedStr = urllib.urlencode(tmphash)
    encodedPattern = re.compile(r"^str=(.*)$")
    encodedSearch = encodedPattern.search(encodedStr)
    encodedStr = encodedSearch.groups()[0]
    encodedStr = encodedStr.replace('.', '%2E')
    encodedStr = encodedStr.replace('-', '%2D')
    encodedStr = encodedStr.replace(',', '%2C')
    return (encodedStr)

def encode_multipart_formdata(fields):
    BOUNDARY = mimetools.choose_boundary()
    #BOUNDARY = '---------------------------146043902159'
    CRLF = '\r\n'
    L = []
    for (key, value) in fields.iteritems():
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    #content_type = 'Content-Type: multipart/form-data; boundary=%s' % BOUNDARY
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    #content_length = 'Content-Length: ' + str(len(body)) + CRLF
    content_length = str(len(body))
    return content_type, content_length, body
"""
This class is responsible for POSTing the data (Story objects) to the PLIGG sites. It will also handle
website registration and website logins. 
"""
class SiteAccountOperator(object):
    supportedEmailServices = ['gmail', 'yahoo', 'ymail', 'rocketmail']

    usernameFieldnamePattern = re.compile(r"(username|user|userid)", re.IGNORECASE)
    passwordFieldnamePattern = re.compile(r"(password|passwd)", re.IGNORECASE)
    password2FieldnamePattern = re.compile(r"(password_?2|passwd_?2|repeat_?passw)", re.IGNORECASE)
    emailFieldnamePattern = re.compile(r"email", re.IGNORECASE)
    checkVerifyPattern = re.compile(r"(check|verify|button)", re.IGNORECASE)

    slashAtBeginingPattern = re.compile(r"^/")
    slashAtEndPattern = re.compile(r"/$")
    registerWordPattern = re.compile(r"register", re.IGNORECASE)

    registrationErrorPatternUsernameExists = re.compile(r"The\s+username\s+requested\s+already\s+exists", re.IGNORECASE)
    registrationErrorPatternEmailIdExists = re.compile(r"Another\s+user\s+with\s+that\s+email\s+address\s+exists", re.IGNORECASE)
    registrationErrorPatternCaptchaMismatch = re.compile(r"The\s+CAPTCHA\s+answer\s+provided\s+is\s+not\s+correct", re.IGNORECASE)
    registrationErrorPatternCaptchaMismatch2 = re.compile(r"The\s+answer\s+provided\s+is\s+not\s+correct\.\s+Please\s+try\s+again", re.IGNORECASE)
    
    def __init__(self, cfgFile, siteUrl=None):
        # Create the opener object(s). Might need more than one type if we need to get pages with unwanted redirects.
        self.opener = urllib2.build_opener() # This is my normal opener....
        self.no_redirect_opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler(), NoRedirectHandler()) # this one won't handle redirects.
        #self.debug_opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1))
        # Initialize some object properties.
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.10) Gecko/20111103 Firefox/3.6.24',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.homeDir = os.getcwd()
        self.websiteUrl = siteUrl
        self.registrationUrl = None
        self.loginPageUrl = None
        self.requestUrl = self.websiteUrl
        self.baseUrl = None
        self.pageRequest = None
        if self.websiteUrl:
            parsedUrl = urlparse(self.requestUrl)
            self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc
            # Here we just get the webpage pointed to by the website URL
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        self.pageResponse = None
        self.requestMethod = "GET"
        self.postData = {}
        self.sessionCookies = None
        self.currentPageContent = None
        if self.websiteUrl:
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
                self.httpHeaders["Cookie"] = self.sessionCookies
            except:
                print __file__.__str__() + ": Couldn't fetch page due to limited connectivity. Please check your internet connection and try again" + sys.exc_info()[1].__str__()
            self.httpHeaders["Referer"] = self.requestUrl
            # Initialize the account related variables...
            self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
            if not self.currentPageContent:
                print "Could not access the website content of " + self.websiteUrl
        self.username = None
        self.password = None
        self.emailId = None
        self.emailPasswd = None
        self.isLoggedIn = False
        self.registered = False
        self.cfgParser = ConfigParser()
        self.cfgParser.read(cfgFile)
        (dbuser, dbpasswd, dbport, dbserver, dbname) = (self.cfgParser.get('Database', 'username'), self.cfgParser.get('Database', 'password'), self.cfgParser.get('Database', 'port'), self.cfgParser.get('Database', 'server'), self.cfgParser.get('Database', 'dbname'))
        self.dbconn = MySQLdb.connect(dbserver, dbuser, dbpasswd, dbname)
        self.cursor = self.dbconn.cursor()
        self.maxOperatorThreadsRegistrations = self.cfgParser.get('ThreadInfo', 'max_registration_threads')
        self.maxOperatorThreadsStoryPost = self.cfgParser.get('ThreadInfo', 'max_story_post_threads')
        self.captchaServiceName = self.cfgParser.get("CaptchaAPI", "servicename")
        self.dbcUsername = self.cfgParser.get("CaptchaAPI", "username")
        self.dbcPassword = self.cfgParser.get("CaptchaAPI", "password")
        self.logFile = self.cfgParser.get("Logging", "logfile")
        self.logPath = self.cfgParser.get("Logging", "logpath")

    def getConfigParserObject(self):
        return (self.cfgParser)

    def setEmailCreds(self, emailId, passwd):
        self.emailId = emailId
        self.emailPasswd = passwd

    def setOperatorContext(self, siteUrl):
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.10) Gecko/20111103 Firefox/3.6.24',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.homeDir = os.getcwd()
        self.websiteUrl = siteUrl
        self.registrationUrl = None
        self.loginPageUrl = None
        self.requestUrl = self.websiteUrl
        parsedUrl = urlparse(self.requestUrl)
        self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc
        # Here we just get the webpage pointed to by the website URL
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        self.pageResponse = None
        self.requestMethod = "GET"
        self.postData = {}
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
            self.httpHeaders["Cookie"] = self.sessionCookies
        except:
            print __file__.__str__() + ": Couldn't fetch page due to limited connectivity. Please check your internet connection and try again" + sys.exc_info()[1].__str__()
            #sys.exit()
        self.httpHeaders["Referer"] = self.requestUrl
        # Initialize the account related variables...
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        self.username = None
        self.password = None
        self.emailId = None
        self.emailPasswd = None
        self.isLoggedIn = False
        self.registered = False
        self.cfgParser = ConfigParser()
        self.cfgParser.read(cfgFile)
        (dbuser, dbpasswd, dbport, dbserver, dbname) = (self.cfgParser.get('Database', 'username'), self.cfgParser.get('Database', 'password'), self.cfgParser.get('Database', 'port'), self.cfgParser.get('Database', 'server'), self.cfgParser.get('Database', 'dbname'))
        self.dbconn = MySQLdb.connect(dbserver, dbuser, dbpasswd, dbname)
        self.cursor = self.dbconn.cursor()
        self.maxOperatorThreads = self.cfgParser.get('ThreadInfo', 'weboperatorthread')
        self.dbcUsername = self.cfgParser.get("CaptchaAPI", "username")
        self.dbcPassword = self.cfgParser.get("CaptchaAPI", "password")
        if not self.currentPageContent:
            print "Could not access the website content of " + self.websiteUrl
            return None
        else:
            return (self.currentPageContent)

    def isRegistered(self):
        self.registrationUrl = self._getRegistrationLink()
        if not self.registrationUrl:
            return None
        sql = "select userId, password from storypost where registrationUrl = '%s'"%self.registrationUrl
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        if rows.__len__() > 0:
            for row in rows:
                if row[0] != 0:
                    self.username = row[1]
                    self.password = row[2]
                    return True
        return False

    def doRegistration(self, usrid, passwd, emailid, emailpasswd, logger=None):
        print "Starting registration..."
        self.registrationUrl = self._getRegistrationLink()
        if usrid == None or passwd == None:
            print "Registration not possible without passing userId and password."
            return None
        else:
            self.username = usrid
            self.password = passwd
            self.emailId = emailid
            self.emailPasswd = emailpasswd
        if not self.__class__.isEmailServiceSupported(self.emailId):
            print "Sorry, the email service you are using is not supported."
            print "We support the following email services: " + ", ".join(self.__class__.supportedEmailServices)
            print "Please specify an email Id with one of these supported services and try again."
            #sys.exit()
            return None
        if not self.registrationUrl: # If we could not find the registration URL, then no use trying to register
            return None
        self.requestUrl = self.registrationUrl
        #print "Registration URL: ", self.requestUrl
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not fetch registration/sign-up page. Please check your internet connectivity before trying again."
            return None
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        self.httpHeaders['Referer'] = self.requestUrl
        # Now find the registration form... It is expected to have an id value of 'thisform'
        soup = BeautifulSoup(self.currentPageContent)
        form = soup.find("form", {'id' : 'thisform'})
        if not form:
            form = soup.find("form", {'name' : 'register'})
        if not form:
            form = soup.find("form", {'id' : 'register'})
        # Handle all cases where the registration form is not found using the above mentioned 'id' and 'name' values.
        if not form:
            form = soup.find("form", {'action' : '/register.php'})
        if not form:
            form = soup.find("form", {'action' : self.__class__.registerWordPattern })
        if not form:
            form = soup.find("form", {'id' : self.__class__.registerWordPattern })
        if not form:    
            form = soup.find("form", {'name' : self.__class__.registerWordPattern })
        # If we did find the form, then check if its 'action' attribute contains the string pattern 'register'
        if form and form.has_key('action') and not self.__class__.registerWordPattern.search(form['action']): # this isn't the form we are looking for...
            form = soup.find("form", {'action' : self.__class__.registerWordPattern }) # Make a last try...
        # If we still didn't find the registration form, write a log warning and return.
        if not form:
            print "Warning: Could not find the registration form in %s"%self.registrationUrl
            return (None)
        formContent = form.renderContents()
        if form.has_key("action"):
            formAction = form['action']
            if not EmailBot._isAbsoluteUrl(formAction):
                formAction = self.baseUrl + formAction
            self.requestUrl = formAction
        #print "Registration Form Action URL: ",self.requestUrl
        no_captcha_flag = False
        # Lets get all input tags in the form's content
        formSoup = BeautifulSoup(formContent)
        allInputTags = formSoup.findAll("input")
        formData = {}
        # Remember, one of these will also be a captcha input... usually the fieldname that we are to send back with the
        # captcha response is called 'recaptcha_challenge_field'. The captcha would be accessed from the 'src' value of
        # the iframe element. Also, the element with the 'recaptcha_challenge_field' name would be a textarea element.
        for inputTag in allInputTags:
            if inputTag.has_key("name") and self.__class__.usernameFieldnamePattern.search(inputTag["name"]):
                formData[inputTag["name"]] = self.username
            elif inputTag.has_key("name") and self.__class__.passwordFieldnamePattern.search(inputTag["name"]):
                formData[inputTag["name"]] = self.password
            elif inputTag.has_key("name") and self.__class__.password2FieldnamePattern.search(inputTag["name"]):
                formData[inputTag["name"]] = self.password
            elif inputTag.has_key("name") and self.__class__.emailFieldnamePattern.search(inputTag["name"]):
                formData[inputTag["name"]] = self.emailId
            elif inputTag.has_key("name") and self.__class__.checkVerifyPattern.search(inputTag["name"]):
                continue
            else:
                if inputTag.has_key("name"):
                    formData[inputTag["name"]] = inputTag.get("value", "").encode('utf-8', 'ignore')
                elif inputTag.has_key("id"):
                    formData[inputTag["id"]] = inputTag.get("value", "").encode('utf-8', 'ignore')
                else:
                    pass
        # Get the iframe tag...
        iframeTag = formSoup.find("iframe") # Expect to get only one iframe in the form.
        iframeSrc = ""
        # Did we get an IFrame ? ? ? This is supposed to be recaptcha
        if iframeTag:
            if iframeTag.has_key("src"):
                iframeSrc = iframeTag.get('src', "") # This will be a api.recaptcha.net url.
            imgSrc = self.__class__._getRecaptchaImageUrl(iframeSrc)
            #print "Iframe URL for %s: %s"%(self.websiteUrl, imgSrc.encode('utf-8', 'ignore'))
            imgSrcParts = imgSrc.split("?c=")
            formData['recaptcha_challenge_field'] = imgSrcParts[1].encode('utf-8', 'ignore')
            recaptcha_response_field = ""
            if self.captchaServiceName.lower() == "deathbycaptcha":
                recaptcha_response_field = self.processCaptchaUsingDBC(imgSrc)
            elif self.captchaServiceName.lower() == "decaptcher":
                recaptcha_response_field = self.processCaptchaUsingDecaptcher(imgSrc)
            else:
                recaptcha_response_field = self.processCaptcha(imgSrc) # Use OCR. This is the least efficient option.
            #print "Captcha String for %s: %s"%(self.websiteUrl, recaptcha_response_field)
            if recaptcha_response_field:
                formData['recaptcha_response_field'] = recaptcha_response_field # Need to fill this up with the captcha text.
        else: # If we didn't get a iframe, then it might be something other than recaptcha...  Do we have an image tag?
            imgTag = formSoup.find("img")
            # Try to identify the captcha text input field here. Most likely, it would be a text field immediately after the captcha image
            if imgTag:
                imgSrc = imgTag.get("src" , '')
                imgSrc = self.websiteUrl[:-1] + imgSrc
                #print "Image URL for %s: %s"%(self.websiteUrl, imgSrc)
                recaptcha_response_field = ""
                if self.captchaServiceName.lower() == "deathbycaptcha":
                    recaptcha_response_field = self.processCaptchaUsingDBC(imgSrc)
                elif self.captchaServiceName.lower() == "decaptcher":
                    recaptcha_response_field = self.processCaptchaUsingDecaptcher(imgSrc)
                else:
                    recaptcha_response_field = self.processCaptcha(imgSrc) # Use OCR. This is the least efficient option.
                if recaptcha_response_field:
                    recaptcha_response_field = recaptcha_response_field.encode('utf-8', 'ignore')
                if logger:
                    logger.write("Captcha Text for %s is %s"%(self.websiteUrl, recaptcha_response_field))
                captchaInputTag = imgTag.findNext("input", {'type' : 'text'})
                captchaInputCode = imgTag.findNext("input", {'type' : 'hidden'})
                captchaFieldname = 'recaptcha_response_field'
                if captchaInputTag:
                    if captchaInputTag.has_key("name"):
                        captchaFieldname = captchaInputTag.get("name")
                    elif captchaInputTag.has_key("id"):
                        captchaFieldname = captchaInputTag.get("id")
                #print "Captcha String for %s: %s"%(self.websiteUrl, recaptcha_response_field)
                if recaptcha_response_field:
                    formData[captchaFieldname] = recaptcha_response_field.encode('utf-8', 'ignore')
                captchaCodeFieldname = "recaptcha_challenge_field"
                if captchaInputCode:
                    if captchaInputCode.has_key("name"):
                        captchaCodeFieldname = captchaInputCode.get("name").encode('utf-8', 'ignore')
                    elif captchaInputCode.has_key("id"):
                        captchaCodeFieldname = captchaInputCode.get("id").encode('utf-8', 'ignore')
                formData[captchaCodeFieldname] = ""
            else: # If we didn't get an image tag either, then maybe, we don't have any challenge from this site at all. This should be rare, though.
                print "Didn't find any captcha challenge for %s"%self.websiteUrl
                no_captcha_flag = True # Sometime you get the captcha on the next page (example: http://www.martial-news.com/register)
        self.postData = formData
        urlencodedPostData = urllib.urlencode(self.postData).encode('ascii', 'ignore')
        #print "POST Data for %s: %s"%(self.websiteUrl, urlencodedPostData)
        # Make the post request
        self.pageRequest = urllib2.Request(self.requestUrl, urlencodedPostData, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            if no_captcha_flag: # This page will contain the captcha...
                self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
                pageSoup2 = BeautifulSoup(self.currentPageContent)
                form = pageSoup2.find("form", {'action' : self.__class__.registerWordPattern})
                if form:
                    formContents = form.renderContents()
                    formSoup2 = BeautifulSoup(formContents)
                    allInputTags = formSoup2.findAll("input")
                    formData = {}
                    formAction2 = form.get('action', self.requestUrl)
                    if not EmailBot._isAbsoluteUrl(formAction2):
                        formAction2 = self.baseUrl + formAction2
                    self.requestUrl = formAction2
                    for inputTag in allInputTags:
                        if inputTag.has_key("name") and self.__class__.usernameFieldnamePattern.search(inputTag["name"]):
                            formData[inputTag["name"]] = self.username
                        elif inputTag.has_key("name") and self.__class__.passwordFieldnamePattern.search(inputTag["name"]):
                            formData[inputTag["name"]] = self.password
                        elif inputTag.has_key("name") and self.__class__.password2FieldnamePattern.search(inputTag["name"]):
                            formData[inputTag["name"]] = self.password
                        elif inputTag.has_key("name") and self.__class__.emailFieldnamePattern.search(inputTag["name"]):
                            formData[inputTag["name"]] = self.emailId
                        elif inputTag.has_key("name") and self.__class__.checkVerifyPattern.search(inputTag["name"]):
                            continue
                        else:
                            if inputTag.has_key("name"):
                                formData[inputTag["name"]] = inputTag.get("value", "").encode('utf-8', 'ignore')
                            elif inputTag.has_key("id"):
                                formData[inputTag["id"]] = inputTag.get("value", "").encode('utf-8', 'ignore')
                            else:
                                pass
                    imgTag = formSoup2.find("img")
                    # Try to identify the captcha text input field here. Most likely, it would be a text field immediately after the captcha image
                    if imgTag:
                        imgSrc = imgTag.get("src" , '')
                        imgSrc = self.websiteUrl[:-1] + imgSrc
                        #print "Image URL for %s: %s"%(self.websiteUrl, imgSrc)
                        recaptcha_response_field = ""
                        if self.captchaServiceName.lower() == "deathbycaptcha":
                            recaptcha_response_field = self.processCaptchaUsingDBC(imgSrc)
                        elif self.captchaServiceName.lower() == "decaptcher":
                            recaptcha_response_field = self.processCaptchaUsingDecaptcher(imgSrc)
                        else:
                            recaptcha_response_field = self.processCaptcha(imgSrc) # Use OCR. This is the least efficient option.
                        if recaptcha_response_field:
                            recaptcha_response_field = recaptcha_response_field.encode('utf-8', 'ignore')
                        formData['ts_code'] = recaptcha_response_field
                        self.postData = formData
                        urlencodedPostData = urllib.urlencode(self.postData).encode('ascii', 'ignore')
                        #print "POST Data (number 2) for %s: %s"%(self.websiteUrl, urlencodedPostData)
                        # Make the post request
                        self.pageRequest = urllib2.Request(self.requestUrl, urlencodedPostData, self.httpHeaders)
                        try:
                            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                        except:
                            print "Could not make the POST request. Error: " + sys.exc_info()[1].__str__()
                            return None
            self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
            self.httpHeaders["Cookie"] = self.sessionCookies
        except:
            print "Could not make the POST request. Error: " + sys.exc_info()[1].__str__()
            return None
        responseHeaders = self.pageResponse.info()
        #print responseHeaders
        locationUrl = responseHeaders.getheader('Location')
        if not locationUrl:
            self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
            if self.__class__.registrationErrorPatternUsernameExists.search(self.currentPageContent):
                print "Registration failed: The username already exists."
            elif self.__class__.registrationErrorPatternEmailIdExists.search(self.currentPageContent):
                print "Registration failed: The emailID is already registered for another user."
            elif self.__class__.registrationErrorPatternCaptchaMismatch.search(self.currentPageContent):
                print "Registration failed: The captcha string was incorrect."
            elif self.__class__.registrationErrorPatternCaptchaMismatch2.search(self.currentPageContent):
                print "Registration failed: The captcha string was incorrect."
            else:
                print "Not sure if the registration process succeeded."
            return(self.currentPageContent)
        if not EmailBot._isAbsoluteUrl(locationUrl):
            self.requestUrl = self.websiteUrl[:-1] + locationUrl
        else:
            self.requestUrl = locationUrl
        
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not send the redirect request to " + self.requestUrl + ". Error : " + sys.exc_info()[1].__str__()
            return None
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        print "The website registration process is successful. Email verification will happen once all websites have been registered with."
        return (self.currentPageContent)


    def processCaptcha(self, captchaUrl):
        captchaResponse = urllib2.urlopen(captchaUrl)
        urlparts = captchaUrl.split(".")
        captchaDumpDir = self.cfgParser.get("Data", "captchadumpdir")
        tmpCaptchaFilename = "captcha_" + int(time.time()).__str__() + ".jpg"
        fc = open(captchaDumpDir + os.path.sep + tmpCaptchaFilename, "wb")
        fc.write(captchaResponse.read())
        fc.close()
        tesseractPath = self.cfgParser.get("Data", "tesseract_dir")
        sys.path.append(tesseractPath) # This is the Tesseract OCR directory
        import pytesser
        curdir = os.getcwd()
        os.chdir(tesseractPath)
        im = pytesser.Image.open(captchaDumpDir + os.path.sep + tmpCaptchaFilename)
        captchaStr = pytesser.image_to_string(im)
        #print captchaStr
        os.chdir(curdir)
        os.unlink(captchaDumpDir + os.path.sep + tmpCaptchaFilename)
        #print "Captcha File: ", captchaDumpDir + os.path.sep + tmpCaptchaFilename
        return (captchaStr)

    def processCaptchaUsingDBC(self, captchaUrl):
        apiPath = os.getcwd() + os.path.sep + "api"
        sys.path.append(apiPath)
        import deathbycaptcha
        try:
            client = deathbycaptcha.SocketClient(self.dbcUsername, self.dbcPassword)
            captchaImageResponse = urllib2.urlopen(captchaUrl)
            captchaImage = captchaImageResponse.read()
            strIoCaptchaImage = StringIO(captchaImage)
            captchaDumpDir = self.cfgParser.get("Data", "captchadumpdir")
            timeout = int(self.cfgParser.get("CaptchaAPI", "timeout"))
            minBal = int(self.cfgParser.get("CaptchaAPI", "minbalance"))
            balance = client.get_balance()
            captcha = client.decode(strIoCaptchaImage, timeout)
            if balance < minBal:
                print "Warning: Your DeathByCaptcha service balance is low. Please renew/recharge the service balance to enjoy uninterrupted service."
            if captcha:
                return (captcha["text"])
        except:
            print "Could not retrieve captcha text from deathbycaptcha service. Please check your credentials or balance." + sys.exc_info()[1].__str__()
            return(None)

    def processCaptchaUsingDecaptcher(self, captchaUrl):
        captchaImageResponse = urllib2.urlopen(captchaUrl)
        captchaImage = captchaImageResponse.read()
        formDataParams = {'function' : 'picture2', 'username' : self.dbcUsername, 'password' : self.dbcPassword, 'pict' : captchaImage, 'pict_to' : '0', 'pict_type' : '0'}
        formDataEncoded = urllib.urlencode(formDataParams)
        headers = {'Content-Type' : 'multipart/form-data', 'Content-Length' : str(len(formDataEncoded))}
        postRequest = urllib2.Request('http://poster.decaptcher.com/', formDataEncoded, headers)
        captchaString = None
        try:
            postResponse = urllib.urlopen(postRequest)
            postResponseContent = postResponse.read()
            responseParts = postResponseContent.split("|")
            if responseParts.__len__() > 5:
                captchaString = responseParts[5]
                print "The returned captcha string from decaptcher is '%s'"%captchaString
            else:
                print "Failed to receive the captcha string from decaptcher. The ResultCode, MajorID and MinorID are: %s, %s and %s"%(responseParts[0], responseParts[1], responseParts[2])
        except:
            print "Failed to make the post request to decaptcher.com. The server returned the following error:\n%s"%(sys.exc_info()[1].__str__())
        return captchaString


    def _getRecaptchaImageUrl(cls, iframeSrcUrl):
        recaptchaResponse = None
        try:
            recaptchaResponse = urllib2.urlopen(iframeSrcUrl)
        except:
            print "Failed to fetch the recaptcha response"
        if not recaptchaResponse:
            print "Did not receive any recaptcha response. "
            return None
        recaptchContent = recaptchaResponse.read()
        recaptchaSoup = BeautifulSoup(recaptchContent)
        imgTag = recaptchaSoup.find("img")
        imgSrc = imgTag.get('src', "")
        if not EmailBot._isAbsoluteUrl(imgSrc):
            imgSrc = "http://api.recaptcha.net/" + imgSrc
        return(imgSrc)
    _getRecaptchaImageUrl = classmethod(_getRecaptchaImageUrl)


    def isEmailServiceSupported(cls, emailId):
        id, service = emailId.split("@")
        service_parts = service.split(".")
        for supportedService in cls.supportedEmailServices:
            if service_parts[0].lower() == supportedService:
                return True
        return False
    isEmailServiceSupported = classmethod(isEmailServiceSupported)


    def getCredentials(self):
        pass


    def getLoginPage(self):
        self.loginPageUrl = self.websiteUrl + "login.php" # Safe assumption... hopefully
        self.requestUrl = self.loginPageUrl
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
            self.httpHeaders["Cookie"] = self.sessionCookies
        except:
            print "Could not fetch the login page... Error: " + sys.exc_info()[1].__str__()
            return None
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        self.httpHeaders["Referer"] = self.loginPageUrl
        return self.currentPageContent


    def doLogin(self, userId, passwd):
        self.username = userId
        self.password = passwd
        print "Attempting to login into %s through login interface page at %s"%(self.websiteUrl, self.loginPageUrl)
        print "Using credentials %s, %s"%(self.username, self.password)
        soup = BeautifulSoup(self.currentPageContent)
        loginForm = soup.find("form", {'id' : "thisform"})
        if not loginForm:
            loginForm = soup.find("form", {'name' : "thisform"})
        if not loginForm:
            loginScriptPattern = re.compile(r"login.php")
            loginForm = soup.find("form", {'action' : loginScriptPattern})
        self.websiteUrl = self.websiteUrl.strip("/")
        self.postData = {}
        if loginForm:
            actionUrl = loginForm.get("action", "")
            if not EmailBot._isAbsoluteUrl(actionUrl):
                actionUrl = self.websiteUrl + actionUrl
            self.requestUrl = actionUrl
            allInputTags = soup.findAll("input")
            for inputTag in allInputTags:
                if inputTag.has_key("name") and self.__class__.usernameFieldnamePattern.search(inputTag['name']):
                    self.postData[inputTag['name']] = self.username
                elif inputTag.has_key("name") and self.__class__.passwordFieldnamePattern.search(inputTag['name']):
                    self.postData[inputTag['name']] = self.password
                elif inputTag.has_key("name") and inputTag['name'] == "processlogin":
                    self.postData['processlogin'] = '1'
                elif inputTag.has_key("name") and inputTag['name'] == "return":
                    self.postData['return'] = ''
                else:
                    continue
            encodedData = urllib.urlencode(self.postData)
            #print "Login POST data for '%s': '%s'"%(self.websiteUrl, encodedData)
            #print "Login POST Headers for '%s': \n"%self.requestUrl, self.httpHeaders
            self.pageRequest = urllib2.Request(self.requestUrl, encodedData, self.httpHeaders)
            self.pageResponse = None
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
                self.httpHeaders["Cookie"] = self.sessionCookies
            except:
                print "Could not send the login post request - Error: " + sys.exc_info()[1].__str__()
                return None
            responseHeaders = self.pageResponse.info()
            locationUrl = responseHeaders.getheader('Location')
            if not locationUrl:
                print "No redirection on login POST request to '%s'"%self.requestUrl
                self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
                self._assertLogin()
                return(self.currentPageContent)
            if not EmailBot._isAbsoluteUrl(locationUrl):
                locationUrl = self.websiteUrl + locationUrl
            self.requestUrl = locationUrl
            #print "Redirecting to '%s' on login POST request for '%s'"%(self.requestUrl, self.websiteUrl)
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Failed to login - Error: " + sys.exc_info()[1].__str__()
                return False
            self.httpHeaders['Referer'] = self.loginPageUrl
            self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
            self._assertLogin()
            return True
        else:
            print "Could not find the login form..."
            return None

    def _assertLogin(self): # Just check to see if the content has an anchor tag with the text 'Logout' in it.
        soup = BeautifulSoup(self.currentPageContent)
        allanchors = soup.findAll("a")
        logoutPattern = re.compile(r"Logout", re.IGNORECASE | re.DOTALL | re.MULTILINE)
        for aTag in allanchors:
            aText = aTag.renderContents()
            #print "ASSERT LOGIN: ", aText
            aText = aText.strip(" ")
            if logoutPattern.search(aText):
                print "Successfully logged into " + self.websiteUrl
                return True
        if logoutPattern.search(self.currentPageContent):
            print "Successfully logged into " + self.websiteUrl
            return True
        print "Not sure if login was successful in " + self.websiteUrl
        return False

    """
    Cookie extractor method to get cookie values from the HTTP response objects. (class method) This
    is an overridden version of the method in EmailBot class. (Reason for overriding: Email service sites
    like yahoo and gmail send cookies with the 'expires and the domain attributes in a different syntax.
    """
    def _getCookieFromResponse(cls, lastHttpResponse):
        cookies = ""
        lastResponseHeaders = lastHttpResponse.info()
        responseCookies = lastResponseHeaders.getheaders("Set-Cookie")
        pathCommaPattern = re.compile(r"path=/;", re.IGNORECASE)
        domainPattern = re.compile(r"Domain=[^;]+", re.IGNORECASE)
        expiresPattern = re.compile(r"Expires=[^;]+;", re.IGNORECASE)
        if responseCookies.__len__() > 1:
            for cookie in responseCookies:
                cookieParts = cookie.split("path=/;")
                cookieParts[0] = re.sub(domainPattern, "", cookieParts[0])
                cookieParts[0] = re.sub(expiresPattern, "", cookieParts[0])
                cookies += "; " + cookieParts[0]
                #print cookieParts[0]
            return(cookies)
    
    _getCookieFromResponse = classmethod(_getCookieFromResponse)

    def _getSubmitStoryPage(self):
        soup = BeautifulSoup(self.currentPageContent)
        allAnchorTags = soup.findAll("a")
        submitStoryUrl = None
        submitStoryLinkPattern = re.compile(r"Submit\s+a\s+new\s+story", re.IGNORECASE | re.DOTALL)
        for aTag in allAnchorTags:
            aContents = aTag.renderContents()
            submitStoryLinkSearch = submitStoryLinkPattern.search(aContents)
            if not submitStoryLinkSearch:
                continue
            submitStoryUrl = aTag.get("href", "")
            if not EmailBot._isAbsoluteUrl(submitStoryUrl):
                submitStoryUrl = self.baseUrl + submitStoryUrl
            break
        if not submitStoryUrl:
            print "Could not get the submit story page in the current content. Guess the url would be " + self.websiteUrl + "/submit.php"
            submitStoryUrl = self.websiteUrl + "/submit.php"
        self.requestUrl = submitStoryUrl
        print "Trying to fetch the story submission interface from %s..."%submitStoryUrl
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not fetch the submit story page for %s - Error: %s"%(self.websiteUrl, sys.exc_info()[1].__str__())
            return None
        self.httpHeaders['Referer'] = self.requestUrl
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        print "Retrieved the story submission interface from %s..."%submitStoryUrl
        return (self.currentPageContent)

    """
    This method will post a story to the website currently being handled by the SiteAccountOperator object.
    """
    def postStory(self, story, storyUrl, storyTags):
        self._getSubmitStoryPage()
        #uniqueNewsUrl = self.cfgParser.get("StoryInfo", "uniquenewsurl")
        uniqueNewsUrl = storyUrl
        # Get the unique News URL form in step #1 and populate it.
        soup = BeautifulSoup(self.currentPageContent)
        allForms = soup.findAll("form")
        formContent = None
        formAction = None
        noneTuple = (None, "")
        print "Negotiating step #1 of story submission for '%s'."%self.baseUrl
        formContent = None
        for form in allForms:
            if form.has_key("name") and form.get("name") == "thisform":
                formContent = form.renderContents()
                formAction = form.get("action", "/submit.php")
                break
            elif form.has_key("id") and form.get("id") == "thisform":
                formContent = form.renderContents()
                formAction = form.get("action", "/submit.php")
                break
            else:
                continue
        if not formContent:
            print "Could not fetch the form in step #1 of story post for %s"%self.baseUrl
            return noneTuple
        formContent = formContent.encode("utf-8", "ignore")
        fsoup = BeautifulSoup(formContent)
        allInputTags = fsoup.findAll("input")
        step1FormData = {}
        for tag in allInputTags:
            if tag.has_key("name") and tag["name"] == "url":
                step1FormData["url"] = uniqueNewsUrl
            elif tag.has_key("id") and tag["id"] == "url":
                step1FormData["url"] = uniqueNewsUrl
            else:
                if tag.has_key("name"):
                    step1FormData[tag["name"]] = tag.get("value", "")
                elif tag.has_key("id"):
                    step1FormData[tag["id"]] = tag.get("value", "")
        # Some websites skip the Step #1, and they lead the user to Step #2 directly. If that is the case, then we would
        # need to look for the "select" tags also.
        selectCat = fsoup.find("select")
        if selectCat and selectCat.has_key("name"):
            selectContent = selectCat.renderContents()
            opSoup = BeautifulSoup(selectContent)
            allOptions = opSoup.findAll("option")
            if allOptions.__len__() > 1:
                step1FormData[selectCat.get("name")] = allOptions[1]["value"]
            else:
                step1FormData[selectCat.get("name")] = ""
        if not EmailBot._isAbsoluteUrl(formAction):
            formAction = self.baseUrl + formAction
        self.requestUrl = formAction
        self.postData = step1FormData
        encodedStep1Data = urllib.urlencode(self.postData)
        # The cookie in header sometimes has a ';' character in the begining.... Eliminate it.
        if self.httpHeaders.has_key('Cookie') and self.httpHeaders['Cookie'] is not None:
             self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].strip(";")
             self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].strip(" ")
        #print "Encoded Step #1 data for %s: %s"%(self.baseUrl, encodedStep1Data.encode("ascii", "ignore"))
        #print "Action URL for Step #1: ", self.requestUrl
        #print "Headers for Step #1: ", self.httpHeaders
        self.pageRequest = urllib2.Request(self.requestUrl, encodedStep1Data, self.httpHeaders)
        self.currentPageContent = None
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Failed to post story in step 1. Error: " + sys.exc_info()[1].__str__()
            return noneTuple
        self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        self.httpHeaders['Referer'] = self.requestUrl
        if not self._verifyStep1():
            return noneTuple
        self.httpHeaders['Referer'] = self.requestUrl
        # Now prepare the request for step #2.
        soup2 = BeautifulSoup(self.currentPageContent)
        allForms2 = soup2.findAll("form")
        formContent2 = None
        formAction2 = "/submit.php"
        print "Negotiating step #2 of story submission for '%s'."%self.baseUrl
        submitPattern = re.compile(r"submit", re.IGNORECASE)
        for form in allForms2:
            if form.has_key("action") and submitPattern.search(form.get("action")):
                formContent2 = form.renderContents()
                formAction2 = form.get("action")
                break
            else:
                continue
        if not formContent2:
            print "Could not retrieve form content for step #2. Aborting attempt to post story."
            return noneTuple
        fsoup2 = BeautifulSoup(formContent2)
        allInputTags2 = fsoup2.findAll("input")
        step2FormData = {}
        storyTitle = ""
        for tag in allInputTags2:
            if tag.has_key("name") and tag["name"] == "url":
                step2FormData["url"] = uniqueNewsUrl
            elif tag.has_key("id") and tag["id"] == "url":
                step2FormData["url"] = uniqueNewsUrl
            elif tag.has_key("name") and tag["name"] == "title":
                step2FormData["title"] = story.getTitle
                storyTitle = step2FormData["title"]
            elif tag.has_key("name") and tag["name"] == "tags":
                step2FormData["tags"] = storyTags
            elif tag.has_key("name") and tag["name"] == "phase":
                step2FormData["phase"] = "2"
            elif tag.has_key("name") and (tag['name'] == "spelling" or tag['name'] == "summarycheckbox" or tag['name'] == "text_num"):
                continue
            elif tag.has_key("name") and tag["name"] == "remLen":
                step2FormData["remLen"] = '0'
            else:
                if tag.has_key("name"):
                    step2FormData[tag["name"]] = tag.get("value", "")
                elif tag.has_key("id"):
                    step2FormData[tag["id"]] = tag.get("value", "")
        step2FormData['bodytext'] = story.getContents
        step2FormData['category'] = ""
        # Find the 'select' tag and get a valid option value
        selectTag = fsoup2.find("select", {'name' : 'category' })
        optVal = ""
        if selectTag:
            selSoup = BeautifulSoup(selectTag.renderContents())
            allOptions = selSoup.findAll("option")
            if allOptions.__len__() > 1:
                optVal = allOptions[1].get("value")
                step2FormData['category'] = optVal
        # Handle captcha field
        iframeTag = fsoup2.find("iframe")
        if not iframeTag:
            iframeTag = fsoup2.find("IFRAME")
        if not iframeTag: # maybe it contains a simple arithmatic puzzle....
            arithPattern = re.compile(r"What\s+is\s+(\d+)\s*\+\s*(\d+)\s*=\s*", re.IGNORECASE)
            arithMatch = arithPattern.search(formContent2)
            if arithMatch:
                num1, num2 = arithMatch.groups()
                ans = int(num1) + int(num2)
                step2FormData['answer'] = ans.__str__() # The field name is 'answer'
        else:
            iframeSrcUrl = iframeTag.get("src", "")
            imgSrcUrl = self.__class__._getRecaptchaImageUrl(iframeSrcUrl)
            imgSrcParts = imgSrcUrl.split("?c=")
            step2FormData['recaptcha_challenge_field'] = imgSrcParts[1]
            recaptcha_response_field = ""
            if self.captchaServiceName.lower() == "deathbycaptcha":
                recaptcha_response_field = self.processCaptchaUsingDBC(imgSrcUrl)
            elif self.captchaServiceName.lower() == "decaptcher":
                recaptcha_response_field = self.processCaptchaUsingDecaptcher(imgSrcUrl)
            else:
                recaptcha_response_field = self.processCaptcha(imgSrcUrl) # Use OCR. This is the least efficient option.
            print "Recaptcha response field during story posting on %s is %s"%(self.baseUrl, recaptcha_response_field)
            step2FormData['recaptcha_response_field'] = recaptcha_response_field.__str__()
        if not EmailBot._isAbsoluteUrl(formAction2):
            formAction2 = self.baseUrl + formAction2
        self.requestUrl = formAction2
        self.postData = step2FormData
        content_type, content_length, encodedStep2Data = encode_multipart_formdata(self.postData)
        tmpHttpHeaders = {}
        self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].strip(";").strip(" ")
        self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].replace("; ;", ";")
        self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].replace("path=/; ", "")
        self.httpHeaders['Cookie'] = self.httpHeaders['Cookie'].strip(";")
        for hkey in self.httpHeaders.keys():
            tmpHttpHeaders[hkey] = self.httpHeaders[hkey]
        tmpHttpHeaders['Referer'] = tmpHttpHeaders['Referer'].encode("ascii", "ignore")
        tmpHttpHeaders['Content-Type'] = content_type
        tmpHttpHeaders['Content-Length'] = content_length
        self.pageRequest = urllib2.Request(self.requestUrl, encodedStep2Data, tmpHttpHeaders)
        #print "Encoded Step #2 Data:\n", encodedStep2Data
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
            # We might get a redirection here...
            responseHeaders = self.pageResponse.info()
            location = responseHeaders.getheader("Location")
            if location:
                if not EmailBot._isAbsoluteUrl(location):
                    location = self.baseUrl + location
                self.requestUrl = location
                tmpHttpHeaders.pop('Content-Length')
                self.pageRequest = urllib2.Request(self.requestUrl, None, tmpHttpHeaders)
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                except:
                    print "Redirection failed during posting story to %s\n"%self.requestUrl
                    return noneTuple
        except:
            print "Failed to clear step #2 - Error: " + sys.exc_info()[1].__str__()
            return noneTuple
        if not self._verifyStep2():
            return noneTuple
        # Now process step #3
        soup3 = BeautifulSoup(self.currentPageContent)
        allForms = soup3.findAll("form")
        formContents3 = None
        formAction3 = None
        for form in allForms:
            if form.has_key("id") and form.get("id") == "thisform":
                formContents3 = form.renderContents()
                formAction3 = form.get("action", "")
                break
            elif form.has_key("name") and form.get("name") == "ATISUBMIT":
                formContents3 = form.renderContents()
                formAction3 = form.get("action", "")
                break
            else:
                continue
        if not EmailBot._isAbsoluteUrl(formAction3):
            formAction3 = self.baseUrl + formAction3
        fsoup3 = BeautifulSoup(formContents3)
        allInputTags3 = fsoup3.findAll("input")
        step3FormData = {}
        for tag in allInputTags3:
            if tag.has_key("name"):
                step3FormData[tag["name"]] = tag.get("value", "")
            else:
                continue
        self.requestUrl = formAction3
        self.postData = step3FormData
        # We will collect the url of the story from here...
        storyUrl = None
        titlePattern = re.compile(r"title", re.IGNORECASE)
        divTag = soup3.find("div", {'class' : 'title'})
        if not divTag:
            divTag = soup3.find("div", {'class' : titlePattern})
        if not divTag:
            divTag = soup3.find("div", {'class' : 'post'})
        if divTag:
            divSoup = BeautifulSoup(divTag.renderContents())
            firstAnchor = divSoup.find("a")
            if firstAnchor and firstAnchor.has_key("href"):
                storyUrl = firstAnchor["href"]
                if not EmailBot._isAbsoluteUrl(storyUrl):
                    storyUrl = self.baseUrl + storyUrl
            encodedStep3Data = urllib.urlencode(self.postData)
            # "Encoded Step #3 Data for %s: %s"%(self.requestUrl, encodedStep3Data)
            self.pageRequest = urllib2.Request(self.requestUrl, encodedStep3Data, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Failed to clear step #3 - Error: " + sys.exc_info()[1].__str__()
                return noneTuple
            self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
        else:
            print "Could not find div tag on step #3 page. Maybe, there is no step #3 on this site (%s)"%self.baseUrl
            storyLinkPattern = re.compile(r"/story.php?title=", re.IGNORECASE)
            storyTitlePattern = re.compile(storyTitle, re.IGNORECASE)
            allAnchorTags = soup3.findAll("a")
            for aTag in allAnchorTags:
                if aTag.has_key("href") and storyLinkPattern.search(aTag['href']):
                    storyUrl = aTag['href']
                    if not EmailBot._isAbsoluteUrl(storyUrl):
                        storyUrl = self.baseUrl + storyUrl
                    break
                aText = aTag.renderContents()
                if storyTitlePattern.search(aText):
                    storyUrl = aTag.get("href")
                    if not EmailBot._isAbsoluteUrl(storyUrl):
                        storyUrl = self.baseUrl + storyUrl
                    break
            return (storyTitle, storyUrl)
        return (storyTitle, storyUrl)


    def castVote(self, storiesCount):
        # First, get the stories info from db...
        getStoriesInfoSql = "select userId, password, storyUrl, storyTitle, storyPostedDate from storypost where websiteUrl='%s'"%(self.websiteUrl)
        self.cursor.execute(getStoriesInfoSql)
        if int(self.cursor.rowcount) == 0:
            print "No records of stories posted on %s exist in the database. No votes will be casted on this website."%self.websiteUrl
            return None
        allRecords = self.cursor.fetchall()
        ctr = 0
        for rec in allRecords:
            if ctr == storiesCount:
                break
            print "Attempting to vote on story titled '%s' (posted as '%s') on website '%s' ..."%(rec[3], rec[0], self.websiteUrl)
            self.requestUrl = rec[2]
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                # Get the anchor tag with 'vote up' class....
                self.currentPageContent = EmailBot._decodeGzippedContent(self.getPageContent())
                psoup = BeautifulSoup(self.currentPageContent)
                voteUpAnchor = psoup.find("a", {'class' : 'vote up'})
                # Get the javascript 'vote' call...
                if voteUpAnchor:
                    voteFuncCall = voteUpAnchor.get("href")
                    # Get the 5 arguments...
                    args = []
                    funcparts = voteFuncCall.split(",")
                    # Get the digits from the first and the last (index 4) arguments...
                    firstSearch = re.compile(r"\((\d+)$").search(funcparts[0])
                    if firstSearch:
                        arg1 = firstSearch.groups()[0]
                        args.append(arg1)
                    args.append(funcparts[1])
                    args.append(funcparts[2])
                    args.append(funcparts[3][1:-1])
                    lastSearch = re.compile(r"^\s*\-?(\d+)\)").search(funcparts[4])
                    if lastSearch:
                        arg4 = lastSearch.groups()[0]
                        args.append(arg4)
                    # Now perform the voting operation as performed by the 'vote' function, i.e send a post request to /vote_total.php...
                    voteRequestUrl = self.baseUrl + "/vote_total.php"
                    votePostArgs = {'user' : args[0], 'id' : args[1], 'md5' : args[3], 'value' : args[4]}
                    votePostArgsEncoded = urllib.urlencode(votePostArgs)
                    voteRequest = urllib2.Request(voteRequestUrl, votePostArgsEncoded, self.httpHeaders)
                    try:
                        voteResponse = self.no_redirect_opener.open(voteRequest)
                        voteResponseContent = voteResponse.read()
                        (voteCount, storyId) = voteResponseContent.split("~--~")
                        print "Story titled '%s' (posted by user '%s') in '%s' has been successfully voted. The vote count for the story is '%s'"%(rec[3], rec[0], self.websiteUrl, voteCount)
                        self.addVoteRecordToDatabase(self.username, self.password, rec[3], rec[0], self.websiteUrl, rec[2], voteCount, rec[4])
                    except:
                        print "The vote request to '%s' for the story titled '%s' failed. The server sent the following reply: '%s'"%(self.websiteUrl, rec[3], sys.exc_info()[1].__str__())
                else: # Couldn't find the vote up anchor, so we will try to find the string 'vote(' in href attrib of anchor tags now
                    allAnchors = psoup.findAll("a")
                    voteFuncPattern = re.compile(r"vote\(")
                    for aTag in allAnchors:
                        if aTag.has_key("href") and voteFuncPattern.search(aTag['href']):
                            voteFuncCall = aTag.get("href")
                            args = []
                            funcparts = voteFuncCall.split(",")
                            # Get the digits from the first and the last (index 4) arguments...
                            firstSearch = re.compile(r"\((\d+)$").search(funcparts[0])
                            if firstSearch:
                                arg1 = firstSearch.groups()[0]
                                args.append(arg1)
                            args.append(funcparts[1])
                            args.append(funcparts[2])
                            args.append(funcparts[3][1:-1])
                            lastSearch = re.compile(r"^\s*\-?(\d+)\)").search(funcparts[4])
                            if lastSearch:
                                arg4 = lastSearch.groups()[0]
                                args.append(arg4)
                            # Now perform the voting operation as performed by the 'vote' function, i.e send a post request to /vote_total.php...
                            voteRequestUrl = self.baseUrl + "/vote_total.php"
                            votePostArgs = {'user' : args[0], 'id' : args[1], 'md5' : args[3], 'value' : args[4]}
                            votePostArgsEncoded = urllib.urlencode(votePostArgs)
                            voteRequest = urllib2.Request(voteRequestUrl, votePostArgsEncoded, self.httpHeaders)
                            try:
                                voteResponse = self.no_redirect_opener.open(voteRequest)
                                voteResponseContent = voteResponse.read()
                                (voteCount, storyId) = voteResponseContent.split("~--~")
                                print "Story titled '%s' (posted by user '%s') in '%s' has been successfully voted. The vote count for the story is '%s'"%(rec[3], rec[0], self.websiteUrl, voteCount)
                                self.addVoteRecordToDatabase(self.username, self.password, rec[3], rec[0], self.websiteUrl, rec[2], voteCount, rec[4])
                            except:
                                print "The vote request to '%s' for the story titled '%s' failed. The server sent the following reply: '%s'"%(self.websiteUrl, rec[3], sys.exc_info()[1].__str__())
                            break
                    print "Could not find the vote icon... Unable to vote."
                ctr += 1
            except:
                print "Could not cast vote for story titled %s on %s website"%(rec[3], self.websiteUrl)
                ctr += 1
                continue
        print "Voted last %s stories in '%s'"%(ctr.__str__(), self.websiteUrl)
        return (True)

    def addVoteRecordToDatabase(self, voteUser, votePass, storyTitle, storyPostUser, websiteUrl, storyUrl, voteCount, storyPostDate):
        voteSql = "insert into storyvote (websiteUrl, voteUserId, votePasswd, storyPosterUserId, votedStoryTitle, votedStoryUrl, voteDate, storyPostDate, voteCount) values ('%s', '%s', '%s', '%s', '%s', '%s', now(), '%s', '%s')"%(websiteUrl, voteUser, votePass, storyPostUser, storyTitle, storyUrl, storyPostDate, voteCount)
        try:
            self.dbconn.begin()
            self.cursor.execute(voteSql)
            self.dbconn.commit()
            return (True)
        except MySQLdb.Error, e:
            print "Insertion into voting table failed, rolling back. SQL Query was:\n%s\nError was:"%(voteSql)
            print e.args
            self.dbconn.rollback()
            return (False)

    def _verifyStep1(self):
        step2of3Pattern = re.compile(r"Step 2\s+of\s+3", re.IGNORECASE | re.MULTILINE | re.DOTALL)
        invalidUrlPattern = re.compile(r"URL\s+is\s+invalid\s+or\s+blocked",  re.IGNORECASE | re.MULTILINE | re.DOTALL)
        step2of3Search = step2of3Pattern.search(self.currentPageContent)
        if step2of3Search:
            print "Completed step #1 successfully"
            return (True)
        else:
            # Do we have a form with enctype as multipart/form-data?
            soup = BeautifulSoup(self.currentPageContent)
            allforms = soup.findAll("form")
            for form in allforms:
                if form.has_key('enctype') and form['enctype'] == "multipart/form-data":
                    return (True) # Possibly this is step #2 page...
            invalidUrlsearch = invalidUrlPattern.search(self.currentPageContent)
            if invalidUrlsearch:
                print "Could not clear step #1 for %s - Error: URL is invalid or blocked"%self.websiteUrl
            else:
                print "Could not clear step #1 for %s - Could not identify the reason"%self.websiteUrl
                #fname = "captcha_images" + os.path.sep + "step1_" + str(int(time.time())) + "_dump.html"
                #f = open(os.getcwd() + os.path.sep + fname, "w")
                #f.write(self.currentPageContent)
                #f.close()
            return (False)

    def _verifyStep2(self):
        step3of3Pattern = re.compile(r"\w+\s+3\s+\w{2,3}\s+3", re.IGNORECASE | re.MULTILINE | re.DOTALL)
        invalidUrlPattern = re.compile(r"URL\s+is\s+invalid\s+or\s+blocked",  re.IGNORECASE | re.MULTILINE | re.DOTALL)
        step3of3Search = step3of3Pattern.search(self.currentPageContent)
        if step3of3Search:
            print "Completed step #2 successfully"
            return (True)
        else:
            soup = BeautifulSoup(self.currentPageContent)
            ptag = soup.find("p", {'class' : 'error'})
            if ptag:
                print "Could not clear step #2 - Error: %s"%ptag.renderContents()
                return (False)
            diverrtag = soup.find("div", { 'class' : 'msg_error'})
            if diverrtag:
                print "Could not clear step #2 - Error: %s"%diverrtag.renderContents()
                return (False)
            invalidUrlsearch = invalidUrlPattern.search(self.currentPageContent)
            if invalidUrlsearch:
                print "Could not clear step #2 - Error: URL is invalid or blocked"
            else:
                print "Could not clear step #2 - Could not identify the reason"
                #fname = "captcha_images" + os.path.sep + "step2_" + str(int(time.time())) + "_dump.html"
                #f = open(os.getcwd() + os.path.sep + fname, "w")
                #f.write(self.currentPageContent)
                #f.close()
            return (False)

   
    def _getRegistrationLink(self):
        if not self.currentPageContent:
            return None
        self.currentPageContent = self.currentPageContent.decode("ascii", "ignore")
        soup = BeautifulSoup(self.currentPageContent)
        allAnchors = soup.findAll("a")
        registerPattern = re.compile(r"\s*(Register|Sign\s+Up|Sign\&nbsp;Up|Join\s+Us|Join\s*)\s*", re.IGNORECASE)
        for atag in allAnchors:
            aText = atag.renderContents()
            registerSearch = registerPattern.search(aText)
            if registerSearch:
                registerLink = atag.get("href")
                if not EmailBot._isAbsoluteUrl(registerLink):
                    if self.__class__.slashAtEndPattern.search(self.baseUrl) or self.__class__.slashAtBeginingPattern.search(registerLink):
                        registerLink = self.baseUrl + registerLink
                    else:
                        registerLink = self.baseUrl + "/" + registerLink
                    registerLink.strip(" ")
                self.registrationUrl = registerLink
                return registerLink
        print "Could not find registration page URL. Trying with the value " + self.websiteUrl + "register"
        registerLink = self.websiteUrl + "register.php"
        return registerLink
        
    def getPageContent(self):
        if self.pageResponse:
            content = self.pageResponse.read()
            # Remove the line with 'DOCTYPE html PUBLIC' string. It sometimes causes BeautifulSoup to fail in parsing the html
            self.currentPageContent = re.sub(r"<.*DOCTYPE\s+html\s+PUBLIC[^>]+>", "", content)
            return(self.currentPageContent)
        else:
            return None

    def voteStory(self, storyUrl):
        pass


class ProxyService(object):
    pass


if __name__ == "__main__":
    ws = SiteAccountOperator(r"..\config\app.cfg")
    #ws = SiteAccountOperator("http://filmjump.com/")
    #rlink = ws._getRegistrationLink()
    #print rlink
    ybot = YahooMailBot()
    ybot.doLogin(ws.emailId, ws.emailPasswd)
    ws.setOperatorContext("http://www.crowd.it/")
    #content = ws.doRegistration("testsup1", "spmprx", r"you_know_who_13@rocketmail.com", "spmprx13")
    content = ws.doRegistration()
    # Do some assertion as to whether the registration succeeded or not.... However, keep
    # in mind that not all the websites require that you verify your registration by clicking
    # link sent to you through email, and some of them do not even send you an email with a
    # link in it. So, for those, you won't find any email in your mailbox, and consequently we
    # assume the registration to be successful by default.
    res = ws.verifyRegistration(ybot)
    if res:
        self.registered = True # If succeeded.
        print "Verified Registration from email Id."
    else:
        print "Could not verify registration. I will try to continue though..."
    if content:
        f = open(r"C:\work\projects\Odesk\PliggStoryPoster\regpage_crowd.html", "w")
        f.write(content)
        f.close()
    ws.setOperatorContext("http://www.mouthrage.com/")
    content = ws.doRegistration()
    res = ws.verifyRegistration(ybot)
    if res:
        self.registered = True # If succeeded.
        print "Verified Registration from email Id."
    else:
        print "Could not verify registration. I will try to continue though..."
    if content:
        f = open(r"C:\work\projects\Odesk\PliggStoryPoster\regpage_mouthrage.html", "w")
        f.write(content)
        f.close()
    sys.exit()
    
