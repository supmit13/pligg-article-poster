import os, sys, re
import urllib, urllib2, htmllib
from urlparse import urlparse
import httplib
from BeautifulSoup import BeautifulSoup
import StringIO
import gzip
import time
import simplejson as json
from EmailBot import EmailBot, NoRedirectHandler



class YahooMailBot(EmailBot):
    
    startUrl=r"https://mail.yahoo.com/"

    """
    Initialization would include fetching the login page of the email service.
    """
    def __init__(self, username="",passwd=""):
        # Create the opener object(s). Might need more than one type if we need to get pages with unwanted redirects.
        self.opener = urllib2.build_opener() # This is my normal opener....
        self.no_redirect_opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler(), NoRedirectHandler()) # ... and this one won't handle redirects. We will mostly use this one for our purpose of scraping the yahoo mail account.
        #self.debug_opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1))
        # Initialize some object properties.
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.10) Gecko/20111103 Firefox/3.6.24',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.homeDir = os.getcwd()
        self.requestUrl = self.__class__.startUrl
        parsedUrl = urlparse(self.requestUrl)
        self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/"
        # First, get the Yahoo mail login page.
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
                    print "Couldn't fetch page due to limited connectivity. Please check your internet connection and try again."
                    sys.exit()
        except:
            print "Couldn't fetch page due to limited connectivity. Please check your internet connection and try again"
            sys.exit()
        self.httpHeaders["Referer"] = self.requestUrl
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        self.httpHeaders["Cookie"] = self.sessionCookies
        # Initialize the account related variables...
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.username = username
        self.password = passwd
        self.isLoggedIn = False
        self.lastChecked = None
        self.currentPageEmailsDict = {} # Holds the dict of emails listed on the page that is being read.
        self.currentPageEmailsDict2 = {} # Holds the dict of emails listed on the page that is being read.
        self.currentFolderLabel = "" # Holds the folder that is currently being read.
        self.currentPageNumber = -1 # Page number of the page that is currently being read.
        self.maxPageNumberCurrentFolder = 0 # Maximum page number for the folder that is currently being processed.
        self.currentInterfaceFormat = "html" # The value would be either "html" or "json". Default is "html". This attribute is also related to the 'newInterface' attribute. If this value is "html", then 'newInterface' has to be False and if it is "json" then 'newInterface' has to be True.
        self._totalEmailsInCurrentFolder = 0
        self.perPageEmailsCount = 25 # By default Yahoo mail displays 25 emails per page.
        self.accountActivity = [] # This will be a list of the memory usage line and the 'Last Account Activity' line.
        self.attachmentLocalStorage = None
        self.newInterface = False # We expect 2 types of interfaces. One is the older HTML interface and the other is the newer ajax interface. By default, we assume it is the older interface.
        self.newInterfaceMessagesList = [] # If 'newInterface' is True, then this list will contain data pertaining to the messages in the inbox (by default, inbox messages from the first page).
        self.wssid = ""
        self.signoutUrl = ""

    """
    Method to perform the login into the user account. It parses the login form to retrieve all the form variables that might be needed,
    builds the 'postData' and then submits the form to the appropriate URL.
    """
    def doLogin(self, username, passwd):
        if username != "":
            self.username = username
        if passwd != "":
            self.password = passwd
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
                if tag["name"] == "login":
                    self.postData[tag["name"]] = self.username
                    continue
                elif tag["name"] == "passwd":
                    self.postData[tag["name"]] = self.password
                    continue
                elif tag["name"] == ".ws":
                    self.postData[tag["name"]] = "1"
                    continue
                else:
                    self.postData[tag["name"]] = ""
            if tag.has_key("value"):
                self.postData[tag["name"]] = tag["value"]
        # Now get the form method and action too..
        if form.has_key("method"):
            self.requestMethod = form.get("method")
        else:
            self.requestMethod = "GET"
        if form.has_key("action"):
            self.requestUrl = form.get("action")
        urlencodedData = urllib.urlencode(self.postData) + "&.save=&passwd_raw=&passwd_raw="
        self.requestUrl = self.requestUrl[:-1]
        self.pageRequest = urllib2.Request(self.requestUrl, urlencodedData, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not post the form data to login - Error: " + sys.exc_info()[1].__str__()
            return None
        # First, get the session cookies...
        self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
        self.httpHeaders["Cookie"] = self.sessionCookies
        self.httpHeaders["Referer"] = self.requestUrl
        # Next, get the content returned with the response... We expect this to be containing a json data structure.
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        # Now, this data structure may be a redirect URL specifier or a Captcha challenge
        jsonDataStructure = json.loads(self.currentPageContent)
        # We expect this data structure to be a dictionary containing the keys 'status' and 'url' and also the values for those.
        if jsonDataStructure.has_key('url'):
            self.requestUrl = jsonDataStructure['url']
        else:
            print "The POST request encountered an error. Probably encountered a captcha."
            return (None)
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not login in to account... Error: " + sys.exc_info()[1].__str__()
            print "Please try again after reviewing your credentials."
            return None
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        # Now, the page content contains a meta http-equiv tag to refresh the page. We need to extract that.
        msoup = BeautifulSoup(self.currentPageContent)
        metaTag = msoup.find("meta", {'http-equiv' : "Refresh"})
        if metaTag and metaTag.has_key("content"):
            metaContent = metaTag.get("content")
            expectedPattern = re.compile(r"^0;\s*url=(.*)$", re.IGNORECASE)
            url = expectedPattern.search(metaContent).groups()[0]
            self.requestUrl = url
        else:
            print "Could not find any meta tag in content."
        tmpHttpHeaders = {}
        # Somehow, the browser skips the 'SSL' cookie. We need to do that, but I have no idea why we should.
        sslCookiePattern = re.compile(r"SSL=([^;]+);")
        for hdr in self.httpHeaders.keys():
            if hdr == "Referer":
                continue
            if hdr == "Cookie":
                cookies = self.httpHeaders['Cookie']
                cookies = re.sub(sslCookiePattern, "", cookies)
                tmpHttpHeaders['Cookie'] = cookies
                continue
            tmpHttpHeaders[hdr] = self.httpHeaders[hdr]
        self.pageRequest = urllib2.Request(self.requestUrl, None, tmpHttpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not login - Error: " + sys.exc_info()[1].__str__()
            return None
        # Now replace the cookie in httpHeaders with the value of the cookie sent
        self.httpHeaders['Cookie'] = tmpHttpHeaders['Cookie']
        self.httpHeaders['Referer'] = self.requestUrl
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.isLoggedIn = self._assertLogin()
        if self.isLoggedIn:
            print "Successfully logged into the account for " + self.username
        return (self.isLoggedIn)


    def _getCookieFromResponse(cls, lastHttpResponse):
        cookies = ""
        responseCookies = lastHttpResponse.info().getheaders("Set-Cookie")
        pathCommaPattern = re.compile(r"path=/,", re.IGNORECASE)
        domainPattern = re.compile(r"Domain=[^;]+;", re.IGNORECASE)
        expiresPattern = re.compile(r"Expires=[^;]+;", re.IGNORECASE)
        if responseCookies.__len__() > 1:
            for cookie in responseCookies:
                cookieParts = cookie.split("path=/")
                cookieParts[0] = re.sub(domainPattern, "", cookieParts[0])
                cookieParts[0] = re.sub(expiresPattern, "", cookieParts[0])
                cookies += cookieParts[0]
            return(cookies)

    _getCookieFromResponse = classmethod(_getCookieFromResponse)

    """
    This method looks for the string 'You are signed in as'. If that is found in the page content,
    the method returns True. Otherwise this method will return False. 
    """
    def _assertLogin(self):
        assertPattern = re.compile(r"You are signed in as", re.MULTILINE | re.DOTALL)
        assertSearch = assertPattern.search(self.currentPageContent)
        if assertSearch:
            return (True)
        else:
            return (False)


    """
    This method looks for the "Check Mail" button on the page and emulates the click event on it. Hence
    this method would be successful only if the page content has the "Check Mail" button somewhere.
    TO DO: This method cannot fetch the login page when the user has changed the skin to some value other than the default.
    """
    def fetchInboxPage(self):
        webPagePath = self.__class__._getPathToPage(self.requestUrl)
        soup = BeautifulSoup(self.currentPageContent)
        foundInboxUrl = False
        # First, we try to find out the form named 'frmChkMailtop'.
        topForm = soup.find("form", {'name' : 'frmChkMailtop'})
        if not topForm:
            self.newInterface = True # First, we rectify our assumption about the interface we are dealing with.
            self.currentInterfaceFormat = "json" # If 'newInterface' is True, then interface format has to be "json".
            # Could not find any form named 'frmChkMailtop'. 
            # Probably we are dealing with a co.<CountryCode> domain (like co.in or co.uk) or rocketmail.com or ymail.com (one with the newer interface)
            # If so, we are already in a page with the inbox emails list. However, we might not be in the proper ('Inbox') tab. But we will get the Inbox tab's
            # data right here in this page. The data for all emails in the inbox will appear after the string "NC.msgListObj=" in this page. Since
            # we expect this to be a json data structure, we will processes it accordingly.
            # Get the content between the <script></script> tags that contain the string 'NC.msgListObj='
            neoConfigPattern = re.compile(r"NC.msgListObj=\s*(.*);NC.msgListTmpl=.*$", re.DOTALL | re.MULTILINE)
            allScriptTags = soup.findAll("script")
            neoConfigContent = ""
            for script in allScriptTags:
                scriptContent = script.renderContents()
                scriptSearch = neoConfigPattern.search(scriptContent)
                if not scriptSearch:
                    continue
                neoConfigContent = scriptSearch.groups()[0]
                break
            # Remove invalid escape characters from content
            neoConfigContent = neoConfigContent.replace("\\ ", "\\")
            jsonNeoConfigData = json.loads(neoConfigContent)
            messagesList = 0
            self.newInterfaceMessagesList = jsonNeoConfigData
            self.currentFolderLabel = "Inbox"
            self.currentPageNumber = 1
            self._totalEmailsInCurrentFolder = self.newInterfaceMessagesList.__len__()
            self.maxPageNumberCurrentFolder = int(self._totalEmailsInCurrentFolder/self.perPageEmailsCount) + 1
            wssidPattern = re.compile(r"wssid:\"([^\"]+)\",", re.DOTALL | re.MULTILINE)
            wssidSearch = wssidPattern.search(self.currentPageContent)
            if not wssidSearch:
                print "Could not retrieve the value of wssid from the page. Can't fetch the target message."
                return None
            self.wssid = wssidSearch.groups()[0]
            foundInboxUrl = True
        else:
            # First, get the request method and action URL (Method is not necessary, but we capture it for the sake of ... whatever!!!)
            if topForm.has_key("method"):
                self.requestMethod = topForm.get("method")
            else:
                self.requestMethod = "GET"
            if topForm.has_key("action"):
                self.requestUrl = topForm.get("action")
            if not self.__class__._isAbsoluteUrl(self.requestUrl):
                self.requestUrl = webPagePath + "/" + self.requestUrl
            foundInboxUrl = True
        if not foundInboxUrl:
            print "Could not find any link to the inbox page"
            return None
        if self.newInterface:
            return (self.currentPageContent)
        self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        try:
            self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
        except:
            print "Could not fetch the inbox page - Error: " + sys.exc_info()[1].__str__()
            return None
        self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
        self.currentFolderLabel = "Inbox"
        self.currentPageNumber = 1
        return (self.currentPageContent)

    """
    This method fetches the spam emails listing page (bulk folder). The contents of the page are
    returned as is, Since we request the result in JSON format, Yahoo sends a JSON output and the
    return value from this method is a JSON data structure. The page fetches the start page by 
    default and contains 20 email messages by default. User may override these values by passing a
    value for the second and third parameters. This method may be called anytime after logging in.
    """
    def fetchSpamPageJSON(self, page_num=1, num_emails=20):
	startInfo = page_num - 1
	self.requestUrl = "http://us.mg5.mail.yahoo.com/ws/mail/v2.0/formrpc?appid=YahooMailNeo&m=ListMessages&o=json&fid=%2540B%2540Bulk&sortKey=date&sortOrder=down&startInfo=" + startInfo.__str__() + "&numInfo=" + num_emails.__str__() + "&wssid=" + self.wssid
	self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
	try:
	    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
	except:
	    print "Could not fetch the spam listing page %s: Error %s\n"%(page_num.__str__(), sys.exc_info()[1].__str__())
	    return None
	self.currentPageContent = self.__class__.decodeGzippedContent(self.getPageContent())
	self.currentFolderLabel = "Spam"
	self.currentPageNumber = page_num
	return (self.currentPageContent)

    """
    This method returns a dictionary comprising of all the folders that the user has created.
    The folder names are the keys and their URLs are the values. The count of unread messages
    in each of these folders appear as a bracketted ("(\d)") entry with the folder names.
    """
    def getCustomFolders(self):
        webPagePath = self.__class__._getPathToPage(self.requestUrl)
        foldersDict = {}
        soup = BeautifulSoup(self.currentPageContent)
        if not self.newInterface:
            orderedListTag = soup.find("ol", {'class' : 'listings custom'})
            if not orderedListTag:
                print "Could not find any custom folders information on this page. Possibly you do not have any."
                return {}
            olContents = orderedListTag.renderContents()
            osoup = BeautifulSoup(olContents)
            allAnchorTags = osoup.findAll("a")
            for atag in allAnchorTags:
                url = ""
                if atag.has_key("href"):
                    url = atag.get("href")
                    if not self.__class__._isAbsoluteUrl(url):
                        url = webPagePath + "/" + url
                folderName = atag.getText()
                foldersDict[folderName] = url
        else:
            foldersPattern = re.compile(r";NC.folders=\s*(.*);NC.mailboxListTmpl=", re.DOTALL | re.MULTILINE)
            allScriptTags = soup.findAll("script")
            foldersData = ""
            for script in allScriptTags:
                scriptContent = script.renderContents()
                folderSearch = foldersPattern.search(scriptContent)
                if not folderSearch:
                    continue
                foldersData = folderSearch.groups()[0]
                break
            foldersDataStruct = json.loads(foldersData)
            if type(foldersDataStruct) == dict and foldersDataStruct.has_key("folder"):
                foldersList = foldersDataStruct['folder']
                for folder in foldersList:
                    if folder.has_key("isSystem") and folder['isSystem']:
                        continue
                    if not folder['isSystem']:
                        folderName = folder['folderInfo']['name']
                        fid = folder['folderInfo']['fid']
                        foldersDict[folderName] = fid
        return(foldersDict)
    

    """
    This method returns a dictionary with the built-in folder names as keys and
    their URLs as values. The count of unread messages in each folder also 
    appears alongwith the names in the keys.
    """
    def getAvailableFolders(self):
        webPagePath = self.__class__._getPathToPage(self.requestUrl)
        foldersDict = {}
        soup = BeautifulSoup(self.currentPageContent)
        if not self.newInterface:
            divTag = soup.find("div", {'id' : 'defaultfolders'})
            if not divTag: # Could not find the available folders.... probably because we have encountered the new yahoo interface.
                return ({}) # TO DO: Handle the new interface here...
            divContents = divTag.renderContents()
            asoup = BeautifulSoup(divContents)
            allAnchorTags = asoup.findAll("a")
            for atag in allAnchorTags:
                url = ""
                if atag.has_key("href"):
                    url = atag.get("href")
                    if not self.__class__._isAbsoluteUrl(url):
                        url = webPagePath + "/" + url
                folderName = atag.getText()
                foldersDict[folderName] = url
        else:
            ulTag = soup.find("ul", {'id' : 'system-folders'})
            ulContents = ulTag.renderContents()
            ulSoup = BeautifulSoup(ulContents)
            allLiTags = ulSoup.findAll("li")
            for liTag in allLiTags:
                liContents = liTag.renderContents()
                liSoup = BeautifulSoup(liContents)
                aTag = liSoup.find("a")
                iTag = liSoup.find("i")
                folderName = iTag.renderContents()
                url = aTag.get("href")
                foldersDict[folderName] = url
        return(foldersDict)
            

    """
    This won't be implemented for Yahoo mail as there is no straight forward method
    to find the date and time at which the current user logged in previously. (In fact,
    I am not sure if yahoo provides that sort of info in any way in their mail service
    interface. Any idea if they do ????)
    """
    def getAccountActivity(self):
        pass


    """
    This method fetches the list of emails on the page currently being processed.
    (The current page content will be in 'currentPageContent' attribute.)
    This method populates the 'currentPageEmailsDict' attribute of the caller object.
    The keys of the dictionary are subjects of the listed emails while the values
    are lists containing the following information in the order specified:
    sender, msgUrl, partialContent, dateReceived.
    Note: Please call this method in a try/except block so that unicode characters
    existing as part of subject lines or message contents do not throw an error.
    TO DO: Add unicode support.
    """
    def listEmailsOnPage(self, folder="Inbox", page=1):
        pageBaseUrl = self.__class__._getPathToPage(self.requestUrl)
        self.currentPageEmailsDict = {}
        self.currentPageEmailsDict2 = {}
        if not self.newInterface:
            soup = BeautifulSoup(self.currentPageContent)
            tableTag = soup.find("table", {"id" : "datatable"})
            if not tableTag:
                print "Could not find any emails in the current folder."
                return ({})
            dataTableContents = tableTag.renderContents()
            dataSoup = BeautifulSoup(dataTableContents)
            allTrs = dataSoup.findAll("tr")
            for tr in allTrs:
                trSoup = BeautifulSoup(tr.renderContents())
                sender, subject, msgUrl, recvdDate, readFlag = (None, None, None, None, True)
                if tr.has_key("class") and tr["class"] == "msgnew":
                    readFlag = False # Unread message
                # Find all td tags in the tr
                allTds = trSoup.findAll("td")
                senderTd = None
                for td in allTds:
                    if td.has_key("title"):
                        senderTd = td
                        break
                sender = ""
                if senderTd:
                    sender = senderTd.get("title")
                h2Tag = trSoup.find("h2")
                if h2Tag:
                    hSoup = BeautifulSoup(h2Tag.renderContents())
                    subjectATag = hSoup.find("a")
                    msgUrl = subjectATag.get("href")
                    subject = subjectATag.renderContents()
                    subject.strip()
                else:
                    subject = ""
                    msgUrl = ""
                if not self.__class__._isAbsoluteUrl(msgUrl):
                    msgUrl = pageBaseUrl + "/" + msgUrl
                dateTdTag = trSoup.find("td", {"class" : "sortcol"})
                recvdDate = ""
                if dateTdTag:
                    recvdDate = dateTdTag.renderContents
                self.currentPageEmailsDict[subject] = [sender, msgUrl, "", recvdDate, readFlag]
                self.currentPageEmailsDict2[msgUrl] = [sender, msgUrl, subject, recvdDate, readFlag]
        else:
            unreadPattern = re.compile(r"unread", re.IGNORECASE)
            for message in self.newInterfaceMessagesList:
                subject = message['subject']
                sender = ""
                if message.has_key("fromObj"):
                    sender = message['fromObj']
                elif message.has_key("from"):
                    senderObj = message["from"]
                    if senderObj.has_key("email"):
                        sender = senderObj["email"]
                    elif senderObj.has_key("name"):
                        sender = senderObj["name"]
                    else:
                        sender = "Unidentified"
                else:
                    sender = "Unidentified"
                mid = message['mid']
                readFlag = 'True'
                flags = ""
                if message.has_key("flags"):
                    flags = message['flags']
                    if type(flags) == dict:
                        if flags["isRead"]:
                            readFlag = 'True'
                        else:
                            readFlag = 'False'
                    elif unreadPattern.search(flags):
                        readFlag = 'False'
                content = "" # TO DO: Figure out how to fetch content.
                partialContent = content + " ..."
                if len(content) > 25:
                    partialContent = content[:25] + " ..." # We will store the first 25 characters as the partial content if content exceeds 25 characters.
                recvdDate = ""
                if message.has_key('rawDate'):
                    recvdDate = message['rawDate'].__str__()
                elif message.has_key('receivedDate'):
                    recvdDate = message['receivedDate'].__str__()
                msgUrl = mid
                self.currentPageEmailsDict[subject] = [sender, msgUrl, partialContent, recvdDate, readFlag]
                self.currentPageEmailsDict2[msgUrl] = [sender, msgUrl, subject, recvdDate, readFlag]
        return(self.currentPageEmailsDict2)


    def getNextPageUrl(self):
        webPagePath = self.__class__._getPathToPage(self.requestUrl)
        nextPageUrl = webPagePath
        if not self.newInterface:
            searchPattern = re.compile(r"Next\s*Page", re.IGNORECASE)
            soup = BeautifulSoup(self.currentPageContent)
            allAnchors = soup.findAll("a")
            for anchor in allAnchors:
                aText = anchor.getText()
                aSearch = searchPattern.search(aText)
                if aSearch:
                    url = anchor.get("href")
                    if not self.__class__._isAbsoluteUrl(url):
                        nextPageUrl += "/" + url
                    else:
                        nextPageUrl = url
                    break
                continue
            return(nextPageUrl)
        else:
            #print "Current Page Number: " + self.currentPageNumber.__str__()
            #print "Total Emails in Current Folder: " + self._totalEmailsInCurrentFolder.__str__()
            #print "Per Page Emails Count: " + self.perPageEmailsCount.__str__()
            if self.currentPageNumber <= int(self._totalEmailsInCurrentFolder / self.perPageEmailsCount) + 1:
                parsedUrl = urlparse(self.requestUrl)
                self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/"
                startNumber = self.currentPageNumber * self.perPageEmailsCount
                endNumber = startNumber + self.perPageEmailsCount
                nextPageUrl = self.baseUrl + "ws/mail/v2.0/formrpc?appid=YahooMailNeo&m=ListMessages&o=json&fid=" + self.currentFolderLabel + "&sortKey=date&sortOrder=down&startInfo=" + startNumber.__str__() + "&numInfo=" + endNumber.__str__() + "&wssid=" + self.wssid
            else:
                nextPageUrl = None # Probably there are no more pages.
            return(nextPageUrl)
        

    def getNextPage(self):
        if not self.newInterface:
            self.requestUrl = self.getNextPageUrl()
            if not self.requestUrl:
                return None
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Could not fetch the next page."
                return None
            self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
            self.currentPageNumber += 1
            return(self.currentPageContent)
        else:
            nextPageUrl = self.getNextPageUrl()
            print "Fetching next page through URL: %s"%nextPageUrl.__str__()
            if not nextPageUrl:
                print "There is no next page."
                return None
            else:
                self.requestUrl = nextPageUrl
                tmpHttpHeaders = {}
                for hk in self.httpHeaders.keys():
                    tmpHttpHeaders[hk] = self.httpHeaders[hk]
                self.pageRequest = urllib2.Request(self.requestUrl, None, tmpHttpHeaders)
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                except:
                    print "Could not fetch next page - Error: " + sys.exc_info()[1].__str__()
                self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
                jsonNeoConfigData = json.loads(self.currentPageContent)
                messagesList = 0
                newMessagesList = None
                if jsonNeoConfigData.has_key("messageInfo"):
                    newMessagesList = jsonNeoConfigData["messageInfo"]
                self.newInterfaceMessagesList = newMessagesList
                self.currentPageNumber += 1
            return(self.currentPageContent)
        

    def getTotalMailsInCurrentFolder(self):
        if not self.newInterface:
            soup = BeautifulSoup(self.currentPageContent)
            divTag = soup.find("div", {'role' : "navigation"})
            expectedPattern = re.compile(r"Messages\s+\d+-\d+\s+of\s+(\d+)")
            divSearch = expectedPattern.search(divTag.getText())
            if not divSearch:
                print "Could not find the total count of emails in current folder"
                return None
            count = divSearch.groups()[0]
            self._totalEmailsInCurrentFolder = count
        return(self._totalEmailsInCurrentFolder)

    """
    Fetches the message content whose URL (or 'mid' for new interface) has been passed in as argument. Returns the message content.
    Note: For the older interface (HTML interface), the content is returned as well as the 'currentPageContent' attribute is
    modified. However, for the newer version, the 'currentPageContent' attribute is not affected since the response is a json
    data structure and assigning that to 'currentPageContent' would not be appropriate. So it would be safer if you use the
    returned value from this method rather than trying to figure what 'currentPageContent' contains after calling it.
    TO DO: Handle unicode.
    """
    def fetchEmailMessage(self, msgUrl):
        if not self.newInterface:
            msgRequest = urllib2.Request(msgUrl, None, self.httpHeaders)
            try:
                msgResponse = self.no_redirect_opener.open(msgRequest)
            except:
                print "Could not fetch the message - Error: " + sys.exc_info()[1].__str__()
                return None
            msgContent = self.__class__._decodeGzippedContent(msgResponse.read())
            return (msgContent)
        else: # If it is the new interface then we need to make a POST request with json data.
            parsedUrl = urlparse(self.requestUrl)
            self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/"
            rval = int(time.time() * 1000)
            msgRequestUrl = self.baseUrl + r"ws/mail/v2.0/jsonrpc?appid=YahooMailNeo&m=GetDisplayMessage&wssid=%s&r=%s"%(self.wssid, rval.__str__())
            jsonData = '{"method":"GetDisplayMessage","params":[{"fid":"Inbox","enableRetry":true,"textToHtml":true,"urlDetection":true,"emailDetection":true,"emailComposeUrl":"mailto:%e%","truncateAt":100000,"charsetHint":"","annotateOption":{"annotateText":"inline"},"message":[{"blockImages":"none","restrictCSS":true,"expandCIDReferences":true,"enableWarnings":true,"mid":"' + msgUrl + '"}]}]}'
            tmpHttpHeaders = {}
            for hk in self.httpHeaders.keys():
                tmpHttpHeaders[hk] = self.httpHeaders[hk]
            tmpHttpHeaders["Content-Type"] = "application/json; charset=UTF-8"
            tmpHttpHeaders["Accept"] = "application/json"
            tmpHttpHeaders["Content-Length"] = len(jsonData)
            tmpHttpHeaders["Pragma"] = "no-cache"
            tmpHttpHeaders["Cache-Control"] = "no-cache"
            msgRequest = urllib2.Request(msgRequestUrl, jsonData, tmpHttpHeaders)
            msgResponse = None
            messageContent = ""
            try:
                msgResponse = self.no_redirect_opener.open(msgRequest)
                messageContent = self.__class__._decodeGzippedContent(msgResponse.read())
            except:
                print "Could not fetch message - Error: " + sys.exc_info()[1].__str__()
                return None
            # Note: messageContent is json data. So you would want to parse it before using it.
            return (messageContent)
        return (None)

    """
    This method enables the user to send emails through the account currently being probed. 'msgDict' is a dictionary
    with the following keys: 'Subject', 'Sender', 'Recipients', 'CcRecipients', 'BccRecipients', 'MessageBody', 'Attachments'.
    The keys are mostly self explanatory. 'Subject' specifies the subject line string, 'Sender' specifies the sender's email
    Id, 'Recipients', 'CcRecipients' and 'BccRecipients' are lists of strings for specifying recipients, cc and bcc fields,
    'MessageBody' specifies the actual message content and 'Attachments' specify the attached filename and its path (if any).
    """
    def sendEmailMessage(self, msgDict):
        webPagePath = self.__class__._getPathToPage(self.requestUrl)
        foundFlag = False
        # First, get the compose page...
        if not self.newInterface:
            soup = BeautifulSoup(self.currentPageContent)
            composePattern = re.compile(r"compose\?&", re.MULTILINE | re.DOTALL)
            allForms = soup.findAll("form")
            for form in allForms:
                if form.has_key("action"):
                    composeSearch = composePattern.search(form["action"])
                    if not composeSearch:
                        continue
                    else:
                        self.requestUrl = webPagePath + "/" + form["action"]
                        foundFlag = True
                        break
            if not foundFlag:
                print "Could not find the 'New' button to compose email. Please check if you are logged out."
                return None
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Could not fetch the page to compose message.... Something didn't work right. Please try again"
                print "If you encounter this problem repeatedly, please let me know (you_know_who_13@rocketmail.com)."
            self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
            # At this point we have the page where we need to type in our email message.
            soup = BeautifulSoup(self.currentPageContent)
            form = soup.find("form", {'name' : "Compose"})
            formSoup = BeautifulSoup(form.renderContents())
            self.requestUrl = webPagePath + "/" + form["action"]
            # Find all input tags
            allInputTags = formSoup.findAll("input")
            textarea = formSoup.find("textarea", {'name' : 'Content'})
            messageData = {}
            for input in allInputTags:
                if input["type"] == "hidden":
                    name = input["name"]
                    messageData[name] = input["value"]
                elif input["type"] == "text":
                    name = input["name"]
                    if name == "to":
                        recipientsString = ",".join(msgDict['Recipients'])
                        messageData[name] = recipientsString
                    elif name == "cc":
                        ccString = ",".join(msgDict['CcRecipients'])
                        messageData[name] = ccString
                    elif name == "bcc":
                        bccString = ",".join(msgDict['BccRecipients'])
                        messageData[name] = bccString
                    elif name == "Subj":
                        subjectString = msgDict['Subject']
                        messageData[name] = subjectString
                    else:
                        if input.has_key("value"):
                            messageData[name] = input["value"]
                        else:
                            messageData[name] = ""
            messageData['Content'] = msgDict['MessageBody']
            # Some specific parameters....
            messageData['ymcjs'] = '1'
            messageData['action_msg_send'] = "Send"
            encodedMessageData = urllib.urlencode(messageData)
            tmpHttpHeaders = {}
            for hk in self.httpHeaders.keys():
                tmpHttpHeaders[hk] = self.httpHeaders[hk]	
            tmpHttpHeaders["Content-Type"] = "application/x-www-form-urlencoded"
            tmpHttpHeaders["Content-Length"] = len(encodedMessageData)
            self.pageRequest = urllib2.Request(self.requestUrl, encodedMessageData, tmpHttpHeaders)
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
            except:
                print "Could not send message - Error: " + sys.exc_info()[1].__str__()
                return None
            self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
            if self._assertMessageSent(self.currentPageContent):
                print "Message sent successfully."
            else:
                # Message could not be sent as yet. That means we might have encountered a captcha or we might have erred elsewhere. First, we try to see if a captcha challenge has been thrown.
                captchaSoup = BeautifulSoup(self.currentPageContent)
                captchaDiv = captchaSoup.find("div", {'id' : 'captchacontent'})
                if not captchaDiv: # Some other error has taken place... We give up our chance to send the email for now.
                    print "Failed to send the message. Try again."
                    return None
                # Captcha challenge encountered. We try to retrieve the captcha image.
                captchaImage = captchaDiv.findNext("img")
                captchaUrl = ""
                if captchaImage and captchaImage.has_key("src"):
                    captchaUrl = captchaImage["src"]
                else:
                    print "Could not find captcha image URL. Check if the captcha container tag ID has changed"
                    return None
                # Add 3 more fields to the POST data ...
                messageData['notFirst'] = '1'
                messageData['send'] = 'Continue'
                messageData['answer'] = "" # This will be the captcha string value. We will now try to solve the captcha and populate this field.
                # Get the captcha file
                captchaRequest = urllib2.Request(captchaUrl, None, self.httpHeaders)
                try:
                    captchaResponse = self.no_redirect_opener.open(captchaRequest)
                except:
                    print "Could not fetch captcha image - Error: " + sys.exc_info()[1].__str__()
                    return None
                ## Solve captcha here....
                captchaImage = captchaResponse.read()
                ## Once that is done, make a POST request again with the data in messageData
                encodedMessageData = urllib.urlencode(messageData)
                tmpHttpHeaders['Content-Length'] = len(encodedMessageData)
                self.pageRequest = urllib2.Request(self.requestUrl, encodedMessageData, tmpHttpHeaders)
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                except:
                    print "Could not send message - Error: " + sys.exc_info()[1].__str__()
                    return None
                self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
                if self._assertMessageSent(self.currentPageContent):
                    print "Message sent successfully."
                else:
                    print "Aborting message send operation."
            return(self.currentPageContent)
        else:
            pass

    def _assertMessageSent(self, pageContent):
        if not self.newInterface:
            soup = BeautifulSoup(pageContent)
            div = soup.find("div", {'class' : 'msgContent'})
            if div:
                h2Text = div.findNext("h2").renderContents()
                if h2Text == "Message Sent":
                    return True
            else:
                return False
        else:
            pass

    """
    This method is basically just a generic version for the fetchInboxPage method. It fetches
    the contents of the page for any folder name that is passed in as argument.
    Status: Yet to be implemented
    """
    def getPage(self, folder="Inbox"):
        pass

    """
    This method will try to retrieve the message pointed to by the 'msgUrl' parameter, and then
    try to get any attachments that might exist in the email.
    Status: Yet to be implemented
    """
    def getAttachmentsFromMessage(self, msgUrl, localDir):
        self.attachmentLocalStorage = localDir


    """
    This method retrieves the list of all the attachments in your emails. By default, it takes you to
    the first page, but specifying a page number will take you to the specified page. It returns the
    HTML of the page which is retrieved.
    Status: Yet to be implemented
    """
    def getAttachmentsPage(self, page=1):
        pass

# Thats it I guess....

# ... and here is a test script
if __name__ == "__main__":
    ybot = YahooMailBot()
    #ybot.doLogin("vns_smitra@yahoo.co.in", "spmprx")
    #ybot.doLogin("supmit13@yahoo.com", "spmprx")
    #ybot.doLogin("supmit2k3@yahoo.com", "xtmt365i")
    #ybot.doLogin("you_know_who_13@rocketmail.com", "spmprx13")
    ybot.doLogin("johnferrier80@rocketmail.com", "spmprx13")
    f = open(r"C:\work\projects\Odesk\PliggStoryPoster\yahooEmails\InboxPage_JF.html", "w")
    f.write(ybot.currentPageContent)
    f.close()
    ybot.fetchInboxPage()
    folders = ybot.getCustomFolders()
    for fkey in folders.keys():
        print fkey, " ======= >> ", folders[fkey]
    print " \n--------------------------------------------------------\n"
    bfolders = ybot.getAvailableFolders()
    for fkey in bfolders.keys():
        print fkey, " ======= >> ", bfolders[fkey]
    count = ybot.getTotalMailsInCurrentFolder()
    emailsDict = ybot.listEmailsOnPage()
    msgUrl = ""
    for msgUrl in ybot.currentPageEmailsDict2.keys():
        try: # Keep in mind that there might be unicode characters in the content or subject...
            sub = ybot.currentPageEmailsDict2[msgUrl][2]
            print "Message URL: " + msgUrl + " ====== URL: " + ybot.currentPageEmailsDict2[msgUrl][2]
        except:
            continue
    #print "Message URL: ", msgUrl
    content = ybot.fetchEmailMessage(msgUrl)
    f = open(r"C:\work\projects\Odesk\PliggStoryPoster\yahooEmails\Message_JF_Page1.html", "w")
    f.write(content)
    f.close()
    ybot.getNextPage()
    f = open(r"C:\work\projects\Odesk\PliggStoryPoster\yahooEmails\MailsList_JF.html", "w")
    f.write(ybot.currentPageContent)
    f.close()
    emailsDict = ybot.listEmailsOnPage()
    msgUrl = ""
    for msgUrl in ybot.currentPageEmailsDict2.keys():
        try: # Keep in mind that there might be unicode characters in the content or subject...
            print "Message URL: " + msgUrl + " ====== URL: " + ybot.currentPageEmailsDict2[sub][2]
            sub = ybot.currentPageEmailsDict2[msgUrl][2]
        except:
            continue
    #print "Message URL: ", msgUrl
    content = ybot.fetchEmailMessage(msgUrl)
    f = open(r"C:\work\projects\Odesk\PliggStoryPoster\yahooEmails\Message_JF_Page2.html", "w")
    f.write(content)
    f.close()
    #msgDict = {'Subject' : 'Script Test AAAAAAAAAAAA', 'Sender' : 'me@me.me', 'Recipients' : ['supmit@gmail.com', 'supmit@rediffmail.com', 'vns_smitra@yahoo.co.in' ], 'MessageBody' : 'This is a test mail sent from the script.... WHATS THIS KOLAVERI KOLAVERI SHIT....', 'CcRecipients' : [], 'BccRecipients' : [], 'Attachments' : ''}
    #ybot.sendEmailMessage(msgDict)
    #f = open(r"C:\work\projects\Odesk\EmailBot\Yahoo\SentMessage2k3.html", "w")
    #f.write(ybot.currentPageContent)
    #f.close()
    #ybot.abracadabra
    


# supmit

