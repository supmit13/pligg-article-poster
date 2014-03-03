import os, sys, re
import urllib, urllib2, htmllib
from urlparse import urlparse
import httplib
from BeautifulSoup import BeautifulSoup
import StringIO
import gzip
import time
from EmailBot import EmailBot, NoRedirectHandler



class GmailBot(EmailBot):
    
    GMAIL_RTT = 4396
    startUrl=r"http://mail.google.com/mail/"
    
    def __init__(self, username="", passwd=""):
        # Create the opener object(s). Might need more than one type if we need to get pages with unwanted redirects.
        self.opener = urllib2.build_opener() # This is my normal opener....
        self.no_redirect_opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler(), NoRedirectHandler()) # ... and this one won't handle redirects. We will mostly use this one for our purpose of scraping the gmail account.
        #self.debug_opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1))
        # Initialize some object properties.
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.10) Gecko/20111103 Firefox/3.6.24',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.homeDir = os.getcwd()
        self.requestUrl = self.__class__.startUrl
        parsedUrl = urlparse(self.requestUrl)
        #self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/"
        self.baseUrl = r"http://mail.google.com/mail/"
        # First, get the Gmail login page.
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        self.pageResponse = None
        self.requestMethod = "GET"
        self.postData = {}
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            headers = self.pageResponse.info()
            if headers.has_key("Location"):
                self.requestUrl = headers["Location"]
                self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                except:
                    print "Couldn't fetch page...."
                    sys.exit()
        except:
            print "Could not fetch page\n"
            sys.exit()
        self.httpHeaders["Referer"] = self.requestUrl
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        self.httpHeaders["Cookie"] = self.sessionCookies
        # Initialize the account related variables...
        self.currentPageContent = GmailBot._decodeGzippedContent(self.getPageContent())
        self.username = username
        self.password = passwd
        self.isLoggedIn = False
        self.lastChecked = None
        # 2 Special cookies we need to remember throughout a session.
        self.gmail_login_cookie = ""
        self.gmail_rtt_cookie = ""
        self.ping_cookie = ""
        self.currentPageEmailsDict = {} # Holds the dict of emails listed on the page that is being read.
        self.currentFolderLabel = "" # Holds the folder that is currently being read.
        self.currentPageNumber = -1 # Page number of the page that is currently being read.
        self.maxPageNumberCurrentFolder = 0 # Maximum page number for the folder that is currently being processed.
        self.currentInterfaceFormat = "ajax" # The value would be "html" if the page is in HTML format, and "ajax" if it is in javascript. The default is "ajax"
        self._totalEmailsInCurrentFolder = 0
        self.perPageEmailsCount = 50 # By default Gmail displays 50 emails per page.
        self.accountActivity = [] # This will be a list of the memory usage line and the 'Last Account Activity' line.
                
 
    def _pingUserRequest(self):
        curtime = int(time.time())
        self.requestUrl = "https://mail.google.com/mail?gxlu=" + self.username + "&zx=" + curtime.__str__() + "000"
        self.ping_cookie = None
        tmpHttpHeaders = {}
        for hkey in self.httpHeaders.keys():
            tmpHttpHeaders[hkey] = self.httpHeaders.get(hkey)
        tmpHttpHeaders['Cookie'] = "GMAIL_RTT=" + self.__class__.GMAIL_RTT.__str__()
        tmpHttpHeaders['Accept'] = "image/png,image/*;q=0.8,*/*;q=0.5"
        self.pageRequest = urllib2.Request(self.requestUrl, None, tmpHttpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except urllib2.HTTPError, e: # This will be HTTP Error 204
            response_headers = e.info()
            # Get the 'Set-Cookie' header from response
            cookies = response_headers.get('Set-Cookie')
            if not cookies:
                print "Could not get the cookie values correctly. Please check your internet connection and try again"
                return self.ping_cookie
            cookieparts = cookies.split("Path=/")
            self.ping_cookie = cookieparts[0]
        # Before returning we must change the Referer header to suit the POST request. The POST request expects the Referer url to be sans arguments.
        urlparts = self.httpHeaders['Referer'].split("?")
        self.httpHeaders['Referer'] = urlparts[0]
        return self.ping_cookie

    """
    This method completes the login process for the user specified by self.username (and whose password is specified in self.password)
    """
    def doLogin(self, username="", password=""):
        if username != "":
            self.username = username
        if password != "":
            self.password = password
        if not self.username or not self.password:
            print "Can't login without credentials. Please set 'username' and 'password' and call again."
            return None
        soup = BeautifulSoup(self.currentPageContent)
        form = soup.find("form")
        # Now we need all the elements... We expect "input" tags only. 
        esoup = BeautifulSoup(form.renderContents())
        inputTags = esoup.findAll("input")
        # Some of the form variables need to be set to specific values for the login to work. On
        # the browser window, the javascript in the page accomplishes this task. 
        for tag in inputTags:
            if tag.has_key("name"):
                tagname = tag["name"]
                self.postData[tagname] = ""
                if tagname == "Email":
                    self.postData[tagname] = self.username + r"@gmail.com"
                elif tagname == "Passwd":
                    self.postData[tagname] = self.password
                elif tagname == "dnConn":
                    self.postData['dnConn'] = "https://accounts.youtube.com/"
                elif tagname == "pstMsg" or tagname == "scc" or tagname == "rmShown":
                    self.postData[tagname] = "1"
                elif tag.has_key("value"):
                    self.postData[tagname] = tag["value"]
                else:
                    self.postData[tagname] = ""
        urlencodedData = urllib.urlencode(self.postData)
        # Before POSTing the form data, gmail sends a ping request to the user. The cookie returned will be stored as self.ping_cookie.
        retval = self._pingUserRequest()
        if not retval:
            print "Could not login probably due to some transient problem"
            return None
        if form.has_key("action"):
            self.requestUrl = form["action"]
        if form.has_key("method"):
            self.requestMethod = form["method"].upper()
        else:
            self.requestMethod = "GET"
        if self.postData.has_key("GALX"):
            self.httpHeaders['Cookie'] += "; GALX=" + self.postData['GALX']
        jsnow = int(time.time())
        jsstart_time = jsnow - GmailBot.GMAIL_RTT
        # The following cookies are usually set by javascript in the page. Here, we need to set them manually.
        self.httpHeaders['Cookie'] += "GMAIL_LOGIN=T" + str(jsstart_time) + "/" + str(jsstart_time) + "/" + str(jsnow)
        self.gmail_login_cookie = "GMAIL_LOGIN=T" + str(jsstart_time) + "/" + str(jsstart_time) + "/" + str(jsnow)
        jsend = int(time.time())
        self.httpHeaders['Cookie'] += "; GMAIL_RTT=" + str(jsend - jsstart_time)
        self.gmail_rtt_cookie = "; GMAIL_RTT=" + str(jsend - jsstart_time)
        self.pageRequest = urllib2.Request(self.requestUrl, urlencodedData, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Couldn't Login.... - Error: " + sys.exc_info()[1].__str__()
            return None
        self.httpHeaders['Referer'] = self.requestUrl
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        self.sessionCookies.rstrip(" ").rstrip(";")
        self.sessionCookies += self.ping_cookie + self.gmail_login_cookie + self.gmail_rtt_cookie
        self.httpHeaders["Cookie"] = self.sessionCookies
        pageContent = GmailBot._decodeGzippedContent(self.getPageContent())
        # The pageContent will have a "<meta http_equiv='refresh'..." tag. We need to follow
        # the URL therein to complete the login operation.
        lsoup = BeautifulSoup(pageContent)
        metaTag = lsoup.find("meta")
        if metaTag.has_key("content"):
            metaContentParts = metaTag['content'].split("url=")
            self.requestUrl = metaContentParts[1]
        else:
            print "Couldn't find the 'meta' tag in the POST response. Possibly one or more of our login params are incorrect"
            return None
        # ==== Eliminate the GAPS=1:... cookie, 'rememberme...' cookie and LSID cookie ========
        cookiesList = self.httpHeaders['Cookie'].split(";")[2:]
        self.httpHeaders['Cookie'] = ""
        for cookie in cookiesList:
            if re.search(r"^\s*$", cookie) or cookie is None:
                continue
            cookieParts = cookie.split("=")
            cookieName, cookieVal = cookieParts[0], cookieParts[1]
            if cookieParts.__len__() > 2:
                cookieName, cookieVal = cookieParts[0], "=".join(cookieParts[1:])
            if cookieName == "LSID" or cookieName == "GAUSR":
                continue
            self.httpHeaders['Cookie'] += cookieName + "=" + cookieVal + "; "
        # ===== GAPS=1:... cookie, 'rememberme...' cookie and LSID cookie eliminated ==========
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Something went wrong in the GET request subsequent to the login POST request - Error: " + sys.exc_info()[1].__str__()
            return None
        pageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        # We expect a HTTP Error 302 (temporary redirect). The redirect URL will be contained in the 'Location' header of the response.
        self.requestUrl = self.pageResponse.info().getheader("Location")
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        # Now we need to eliminate the expired GMAIL_RTT cookie and add the GMAIL_AT and GX cookies from the last response headers.
        cookiesList = self.httpHeaders['Cookie'].split(";")
        for cookie in cookiesList:
            if re.search(r"^\s*$", cookie) or cookie is None:
                continue
            cookieParts = cookie.split("=")
            cookieName, cookieVal = cookieParts[0], cookieParts[1]
            if cookieParts.__len__() > 2:
                cookieName, cookieVal = cookieParts[0], "=".join(cookieParts[1:])
            if cookieName == "GMAIL_RTT":
                continue
            self.httpHeaders['Cookie'] += cookieName + "=" + cookieVal + "; "
        if not self.sessionCookies or self.sessionCookies == "":
            print "Could not get the cookies correctly. Please ensure you are connected to the internet before trying again"
            return (None)
        sessionCookiesList = self.sessionCookies.split(";")
        for sessCookie in sessionCookiesList:
            if re.search(r"^\s*$", sessCookie) or sessCookie is None:
                continue
            sessCookieParts = sessCookie.split("=")
            sessCookieName, sessCookieValue = sessCookieParts[0], sessCookieParts[1]
            if sessCookieParts.__len__() > 2:
                sessCookieName, sessCookieValue = sessCookieParts[0], "=".join(sessCookieParts[1:])
            if sessCookieName == "GMAIL_RTT":
                continue
            self.httpHeaders['Cookie'] += sessCookieName + "=" + sessCookieValue + "; "
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Something went wrong while fetching the inbox emails list page - Error: " + sys.exc_info()[1].__str__()
            return None
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.lastRequestUrl = self.requestUrl
        if self.isLoginSuccessful():
            self.currentFolderLabel = "inbox"
            self.currentPageNumber = 1
        return(self.isLoggedIn)
        

    """
    The following method checks to see if the user has been able to login successfully or not.
    It returns a boolean 'True' if login was successful and a boolean value  of 'False' if not.
    """
    def isLoginSuccessful(self):
        bsoup = BeautifulSoup(self.currentPageContent)
        div = bsoup.find("div", {"class" : "msg"})
        if div:
            divContent = div.renderContents()
            userEmailIdPattern = re.compile(self.username + r"@gmail.com", re.IGNORECASE)
            usernameSearch = userEmailIdPattern.search(divContent)
            if usernameSearch:
                print "Successfully Logged in as " + self.username + "@gmail.com"
                self.isLoggedIn = True
            else:
                print "Login Failed!"
        else:
            print "Could not login into Gmail as " + self.username + "@gmail.com"
        return (self.isLoggedIn)

    """
    Checks if the format of the page is javascript/ajax or basic HTML.
    This method is specific to GmailBot only. 
    """
    def _checkInterfaceFormat(self):
        soup = BeautifulSoup(self.currentPageContent)
        divTag = soup.find("div", {"id" : "stb"})
        divContents = ""
        if divTag:
            divContents = divTag.renderContents()
        divSoup = BeautifulSoup(divContents)
        # We expect an "a" tag in this.
        aTag = divSoup.find("a")
        ahref = ""
        aContents = ""
        if aTag and aTag.has_key("href"):
            ahref = aTag.get("href")
            aContents = aTag.renderContents()
        else:
            return None # Could not identify the interface format
        if aContents == "Load basic HTML": #
            self.currentInterfaceFormat = "ajax"
        else:
            self.currentInterfaceFormat = "html"
        return(ahref)


    """
    This method first checks to see what format the interface is in. Gmail, by default, displays content
    as ajax/javascript. Such content is difficult to parse since the data is in the form of list variables.
    If the content received is in such (ajax/javascript) format, then this method tries to set the UI format
    to plain HTML (which is much easier to parse). This method is specific to GmailBot only. It returns a
    boolean value of 'True' if it successfully changes the format to HTML and 'False' if it can't. As a side
    effect, it also sets the attribute 'currentInterfaceFormat' to the appropriate value.
    """
    def setBasicHTMLView(self):
        uiUrl = self._checkInterfaceFormat()
        screenReaderUrl = ""
        if not self.__class__._isAbsoluteUrl(uiUrl):
            urlparts = self.lastRequestUrl.split("?")
            uiUrl = urlparts[0] + uiUrl
        screenReaderUrl = uiUrl[:-1] + "s"
        #print "Screen Reader URL: ",screenReaderUrl
        if self.currentInterfaceFormat == "ajax":
            self.requestUrl = screenReaderUrl
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Could not set the interface to basic HTML"
                return False
            responseHeaders = self.pageResponse.info()
            if responseHeaders.has_key("Location"):
                self.httpHeaders['Referer'] = self.requestUrl
                self.requestUrl = responseHeaders.get("Location")
                self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                    self.httpHeaders['Referer'] = self.requestUrl
                except:
                    print "Could not set the interface to basic HTML"
                    return False
            self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
            self.currentInterfaceFormat = "html"
            self.lastRequestUrl = self.requestUrl
            return True
        else:
            return True
                    
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

    """
    The following method lists the emails on a specific page for the folder specified. By default,
    it lists the emails in the Inbox folder's first page. If you would like to list out all emails
    on the 3rd page of your sent items folder, then your call would look something like the following:
    listOfEmailsSent = gm.listEmail("SentItems"). It populates a dictionary 'currentPageEmailsDict' 
    with the list of emails fetched from the targetted page. The dictionary keys are the subject lines
    while the values would be lists comprising of the following items: i) Sender's name or email Id, ii)
    URL of the actual email message, iii) Part of the content that is normally listed with the emails
    list in gmail, iv) Date and Time at which the message was received.
    """
    def listEmailsOnPage(self, folder="Inbox", page=1):
        pageBaseUrl = self.__class__._getPageBaseURL(self.currentPageContent)
        soup = BeautifulSoup(self.currentPageContent)
        tableTag = soup.find("table", {'class' : 'th'})
        if not tableTag:
            print "Doesn't find any email on the current page."
            return(None)
        else:
            tableContents = tableTag.renderContents()
            tsoup = BeautifulSoup(tableContents)
            allTrs = tsoup.findAll("tr")
            # Every email has attributes specified in 4 tds. The first one contains a checkbox and we need to skip it.
            for tr in allTrs:
                tdsoup = BeautifulSoup(tr.renderContents())
                allTds = tdsoup.findAll("td")
                tdctr = 1
                sender, subject, contents, datetime, url = ("", "", "", "", "")
                for td in allTds:
                    if tdctr == 1:
                        tdctr = 2
                        continue
                    elif tdctr == 2:
                        sender = td.getText()
                        tdctr += 1
                        continue
                    elif tdctr == 3:
                        contentsoup = BeautifulSoup(td.renderContents())
                        aTag = contentsoup.find("a")
                        if aTag and aTag.has_key("href"):
                            url = aTag.get("href")
                            if not self.__class__._isAbsoluteUrl(url):
                                url = pageBaseUrl + url
                        bTag = contentsoup.find("b")
                        if bTag:
                            subject = bTag.renderContents()
                        content = aTag.renderContents()
                        fontTag = contentsoup.find("font", {'color' : '#7777CC'})
                        if fontTag:
                            content = fontTag.renderContents()
                        tdctr += 1
                        continue
                    elif tdctr == 4:
                        datetime = td.renderContents()
                        datetime = datetime.replace("&nbsp;", " ")
                        tdctr += 1
                        continue
                self.currentPageEmailsDict[subject] = [ sender, url, content, datetime ]
        return(self.currentPageEmailsDict)
    

    def getMaxPageNumberInCurrentFolder(self):
        if self._totalEmailsInCurrentFolder == 0:
            self.getTotalMailsInCurrentFolder()
        pagesCount = int(int(self._totalEmailsInCurrentFolder) / int(self.perPageEmailsCount)) + 1
        self.maxPageNumberCurrentFolder = pagesCount
        return(pagesCount)
        
    def getAccountActivity(self):
        soup = BeautifulSoup(self.currentPageContent)
        table = soup.find("table", {'class' : 'ft'})
        ssoup = BeautifulSoup(table.renderContents())
        span = ssoup.find("span")
        self.accountActivity.append(span.renderContents())
        div = ssoup.find("div")
        self.accountActivity.append(div.renderContents())
        return (self.accountActivity)


    """
    This method gets the URL to the next page for the current Folder/Label being accessed.
    """
    def getNextPageUrl(self):
        soup = BeautifulSoup(self.currentPageContent)
        pageBaseUrl = self.__class__._getPageBaseURL(self.currentPageContent)
        inputTag = soup.find("input", {'name' : 'nvp_tbu_go'})
        if not inputTag:
            return None
        else:
            tdTag = inputTag.findNext("td")
            tdContents = tdTag.renderContents()
            tdSoup = BeautifulSoup(tdContents)
            nexta = tdSoup.find("a")
            if not nexta:
                return None
            if nexta.has_key("href"):
                nextPageUrl = nexta.get("href")
                if not self.__class__._isAbsoluteUrl(nextPageUrl):
                    nextPageUrl = pageBaseUrl + nextPageUrl
                return(nextPageUrl)
            else:
                return ("")


    """
    Gets the contents of the next page for the folder/label in which the user is currently browsing.
    This enables the user to sequentially access pages in the account.
    """
    def getNextPage(self):
        self.requestUrl = self.getNextPageUrl()
        if not self.requestUrl:
            print "There are no more pages in this folder"
            return(self.currentPageContent)
        self.httpHeaders['Referer'] = self.lastRequestUrl
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            self.currentPageNumber += 1
        except:
            print "Could not fetch the next page (Page number %s)"%(self.currentPageNumber + 1).__str__()
            return None
        self.currentPageEmailsDict = {}
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.lastRequestUrl = self.requestUrl
        return (self.currentPageContent)
    

    """
    This method returns the count of emails in the folder currently being accessed. The current folder is
    specified by the obj.currentFolderLabel variable. This method returns None if it fails to find the count,
    and returns the count if it succeeds. Also, as a side effect, this method also populates the 'perPageEmailsCount'
    attribute of the 'GmailBot' object.
    """
    def getTotalMailsInCurrentFolder(self):
        soup = BeautifulSoup(self.currentPageContent)
        inputTag = soup.find("input", {'name' : 'nvp_tbu_go'})
        if not inputTag:
            return None
        else:
            tdTag = inputTag.findNext("td")
            tdText = tdTag.getText()
            tdText = tdText.replace("&nbsp;", "")
            expectedPattern = re.compile(r"(\d+)\-(\d+)\s*of\s*(\d+)\D", re.IGNORECASE)
            expectedPatternSearch = expectedPattern.search(tdText)
            if expectedPatternSearch:
                emailsCount = expectedPatternSearch.groups()[2]
                self._totalEmailsInCurrentFolder = emailsCount
                lowerCount = expectedPatternSearch.groups()[0]
                higherCount = expectedPatternSearch.groups()[1]
                self.perPageEmailsCount = int(higherCount) - int(lowerCount) + 1
                return (emailsCount)
            else:
                return None

    """
    This method will enable the user to go to a page randomly. 
    """
    def getPage(self, url):
        pass


    """
    This method will fetch the textual content of the specified email message. The email should be
    specified by its URL. Thus, you need to call the 'listEmailsOnPage' method prior to calling this
    method.
    """
    def fetchEmailMessage(self, msgUrl):
        self.requestUrl = msgUrl
        self.httpHeaders['Referer'] = self.lastRequestUrl
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not fetch the message. Error: " + sys.exc_info()[1].__str__()
            return None
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.lastRequestUrl = self.requestUrl
        return (self.currentPageContent)


    """
    This method retrieves the folders that the logged in user has in her/his account.
    The return value is a dictionary, with folder names are the keys and their URLs are values.
    """
    def getAvailableFolders(self):
        pageBaseUrl = self.__class__._getPageBaseURL(self.currentPageContent)
        uiUrl = self._checkInterfaceFormat()
        foldersDict = {}
        if self.currentInterfaceFormat == "ajax":
            print "The current interface is 'ajax'. In order for this function to work, you need to set the UI to 'html'."
            print "You can do that by calling 'setBasicHTMLView' method on the object that made this call."
            return None
        elif self.currentInterfaceFormat == "html":
            soup = BeautifulSoup(self.currentPageContent)
            tableM = soup.find("table", {'class' : 'm'})
            if not tableM:
                return None
            tableContents = tableM.renderContents()
            fsoup = BeautifulSoup(tableContents)
            h2tag = fsoup.find("h2", {'class' : 'hdn'})
            anchors = fsoup.findAll("a")
            for atag in anchors:
                if not atag.has_key("href"):
                    continue
                ahref = atag.get("href")
                atext = atag.getText()
                atext = atext.replace("&nbsp;", "")
                if not self.__class__._isAbsoluteUrl(ahref):
                    ahref = pageBaseUrl + ahref
                foldersDict[atext] = ahref
            return (foldersDict)
        else:
            print "Unsupported interface format."
            return None
    

    """
    This method retrieves the labels that the logged in user has in her/his account.
    The return value is a dictionary, with label names are the keys and their URLs are values.
    """
    def getAvailableLabels(self):
        pageBaseUrl = self.__class__._getPageBaseURL(self.currentPageContent)
        uiUrl = self._checkInterfaceFormat()
        labelsDict = {}
        if self.currentInterfaceFormat == "ajax":
            print "The current interface is 'ajax'. In order for this function to work, you need to set the UI to 'html'."
            print "You can do that by calling 'setBasicHTMLView' method on the object that made this call."
            return None
        elif self.currentInterfaceFormat == "html":
            soup = BeautifulSoup(self.currentPageContent)
            labelsTD = soup.find("td", {'class' : 'lb'})
            if not labelsTD:
                return labelsDict
            labelsTDContent = labelsTD.renderContents()
            lsoup = BeautifulSoup(labelsTDContent)
            anchors = lsoup.findAll("a")
            labelUrlPattern = re.compile(r"l=(\w+)$")
            for atag in anchors:
                if atag.has_key("href"):
                    ahref = atag.get("href")
                    ahref.strip()
                    labelSearch = labelUrlPattern.search(ahref)
                    if labelSearch:
                        labelName = labelSearch.groups()[0]
                        if not self.__class__._isAbsoluteUrl(ahref):
                            ahref = pageBaseUrl + ahref
                        labelsDict[labelName] = ahref
                    else:
                        continue
                else:
                    continue
            return(labelsDict)
        else:
            return (None)


    def searchEmails(self):
        pass

    """
    This method will try to retrieve the message pointed to by the 'msgUrl' parameter, and then
    try to get any attachments that might exist in the email.
    """
    def getAttachmentsFromMessage(self, msgUrl, localDir):
        self.attachmentLocalStorage = localDir


    
if __name__ == "__main__":
    gbot = GmailBot()
    html = gbot.getPageContent()
    #gbot.doLogin("supmit", "xtmt365i")
    gbot.doLogin("codexaddict", "spmprx13")
    gbot.setBasicHTMLView()
    labels = gbot.getAvailableLabels()
    print "LABELS LIST: "
    for lkey in labels.keys():
        print lkey, " =========== ", labels[lkey]
    folders = gbot.getAvailableFolders()
    print "FOLDERS LIST: "
    for fkey in folders.keys():
        print fkey, " =========== ", folders[fkey]
    count = gbot.getTotalMailsInCurrentFolder()
    print "Total Emails In Current Folder: ", count
    print "Emails Listed Per Page: ", gbot.perPageEmailsCount
    pagesCount = gbot.getMaxPageNumberInCurrentFolder()
    print "Total Number of pages: ", pagesCount
    nextPageUrl = gbot.getNextPageUrl()
    print "Next Page URL: ", nextPageUrl
    gbot.getAccountActivity()
    print gbot.accountActivity[0]
    print gbot.accountActivity[1]
    gbot.getNextPage()
    emailDict = gbot.listEmailsOnPage()
    lastsub = ""
    for sub in emailDict.keys():
        print "Subject: ", sub
        lastsub = sub
        print "Sender: ", emailDict[sub][0]
        print "URL: ", emailDict[sub][1]
        print "Contents: ", emailDict[sub][2]
        print "Date & Time: ", emailDict[sub][3]
        print "======================================================="
    gbot.fetchEmailMessage(emailDict[lastsub][1])
    f = open(r"C:\work\projects\Odesk\EmailBot\Gmail\HTMLMessagePageCodexAddict.html", "w")
    f.write("Subject Line: " + lastsub + "\n\n")
    f.write(gbot.currentPageContent)
    f.close()


# supmit


