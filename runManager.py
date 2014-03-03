import os, sys, re, time
import MySQLdb
from handlers.contents import *
from handlers.webops import *
from Tkinter import *
from threading import Thread
from handlers.logsHandler import Logger
import simplejson as json



class RunManager(object):
    sitesCredsDict = {}
    def __init__(self):
        self.weboperator = SiteAccountOperator("config" + os.path.sep + "app.cfg")
        cfgParser = self.weboperator.getConfigParserObject()
        self.spinner = None
        self.storyQueue = []
        self.sitesQueue = []
        self.usernameQueue = []
        self.mailbot = None
        self.maxOperatorThreadsRegistrations = self.weboperator.maxOperatorThreadsRegistrations
        self.maxOperatorThreadsStoryPost = self.weboperator.maxOperatorThreadsStoryPost
        self.successfulRegistrations = []
        self.successfulLinkVerifications = []
        self.successfulStoryPosts = []
        self.logfile = self.weboperator.logPath + os.path.sep + self.weboperator.logFile
        self.logger = Logger(self.logfile)
        self.registrationThreadsDict = {}
        self.storyPostThreadsDict = {}
        self.newsUrl = ""
        self.newsTags = ""
        self.userId = ""
        self.passwd = ""
        self.emailId = ""
        self.emailPasswd = ""
        self.usrVotePrev = False
        self.setVoteStoriesCount = 0
        self.bgGoogleSearch = False
        self.bgGoogleSearchKeywords = ""

    def getStoryParams(self, content, newsUrl, newsTags):
        self.spinner = ContentSpinner(content)
        self.newsUrl = newsUrl
        self.newsTags = newsTags

    def getRegistrationParams(self, userIdList, passwd, emailId, emailPasswd):
        self.userId = ""
        for userId in userIdList:
            self.usernameQueue.append(userId)
        self.passwd = passwd
        self.emailId = emailId
        self.emailPasswd = emailPasswd
        
    def enqueueStories(self):
        storyCount = 5000
        storyCtr = 0
        while True:
            story = self.spinner.generateStory()
            self.storyQueue.append(story)
            storyCtr += 1
            if storyCtr >= storyCount:
                print self.storyQueue.__len__().__str__() + " stories in queue."
                return True

    def getEmailBotType(self):
        emailid = self.emailId
        emailIdParts = emailid.split("@")
        if emailIdParts.__len__() > 1:
            domainParts = emailIdParts[1].split(".")
            if domainParts[0].lower() == "gmail":
                return('GmailBot')
            elif domainParts[0].lower() == "yahoo" or domainParts[0].lower() == "ymail" or domainParts[0].lower() == "rocketmail":
                return('YahooMailBot')
            else:
                return (None)

    def _formatEmailsList(self, allLines):
        urlpattern = re.compile(r"^(http://[^/]+/).*$")
        modLines = []
        for line in allLines:
            urlsearch = urlpattern.search(line)
            if urlsearch:
                modline = urlsearch.groups()[0]
                modLines.append(modline)
        return(modLines)

    def createSitesQueue(self, sitesText):
        sitesList = sitesText.split("\n")
        # We only need the website URLs (indirectly pointing to the website's index page).
        sitesList = self._formatEmailsList(sitesList)
        uniqueSitesDict = {}
        for site in sitesList:
            site = site.strip(" ")
            if not uniqueSitesDict.has_key(site):
                self.sitesQueue.append(site)
                uniqueSitesDict[site] = 1
        return (self.sitesQueue.__len__())


    def handleRegistration(self, siteUrl, threadCtr):
        configFile = r"config" + os.path.sep + "app.cfg"
        webop = SiteAccountOperator(configFile, siteUrl)
        self.logger.write("Registration Thread Id " + self.registrationThreadsDict[threadCtr.__str__()].__str__() + " starting - URL: " + siteUrl + " Creds: " + self.userId + "/" + self.passwd)
        userId, passwd = (self.userId, self.passwd)
        self.__class__.sitesCredsDict[siteUrl] = (userId, passwd)
        reg = webop.doRegistration(userId, passwd, self.emailId, self.emailPasswd,self.logger)
        tid = self.registrationThreadsDict[threadCtr.__str__()]
        if not reg:
            del self.registrationThreadsDict[threadCtr.__str__()]
            self.logger.write("Registration Failed. Thread Id " + tid.__str__() + " exiting... ")
            return (tid)
        self.logger.write("Registration process in %s successful using username '%s' and password '%s'. Link verification in email will happen in the next phase once all registrations have been handled."%(webop.websiteUrl, userId, passwd))
        self.registrationThreadsDict[threadCtr.__str__()] = None
        self.logger.write("Registration Thread Id " + tid.__str__() + " exiting...")
        self.successfulRegistrations.append(siteUrl)
        return (tid)

    def handleEmailLinkVerifications(self):
        configFile = r"config" + os.path.sep + "app.cfg"
        webop = SiteAccountOperator(configFile)
        botType = self.getEmailBotType()
        if botType == "YahooMailBot":
            self.mailbot = YahooMailBot()
            self.mailbot.doLogin(self.emailId, self.emailPasswd)
        elif botType == "GmailBot":
            self.mailbot = GmailBot()
            self.mailbot.doLogin(self.emailId, self.emailPasswd)
        else:
            self.logger.write("Unsupported email service. Please use yahoo or gmail.")
            #sys.exit()
            return None
        # We will try to keep a record of which of the websites in self.successfulRegistrations can be verified. We will read all unread emails in the account.
        self.mailbot.fetchInboxPage()
        while True:
            emailsDict = self.mailbot.listEmailsOnPage()
            self.logger.write("Inbox Page # %s: %s emails"%(self.mailbot.currentPageNumber.__str__(), emailsDict.keys().__len__().__str__()))
            for mailUrl in self.mailbot.currentPageEmailsDict2.keys():
                mailUrl = mailUrl.encode('ascii', 'ignore')
                if self.mailbot.currentPageEmailsDict2[mailUrl].__len__() >= 4 and self.mailbot.currentPageEmailsDict2[mailUrl][4] == 'False':
                    self.logger.write("Message URL: %s"%mailUrl)
                    sub = self.mailbot.currentPageEmailsDict2[mailUrl][2]
                    sub = sub.encode('ascii', 'ignore')
                    content = self.mailbot.fetchEmailMessage(mailUrl)
                    # Now get the HTML content between "<div id=yiv" and '<div id="contentbuttonbarbottom"'
                    relevantContent = ""
                    if not content:
                        continue
                    if not self.mailbot.newInterface:
                        try:
                            relevantContent = content.split("<div id=yiv")[1].split('<div id="contentbuttonbarbottom"')[0]
                        except:
                            continue # if the above strings are not there, then probably we don't need this email
                        # Fetch all anchor tags in 'relevantContent' and access them... It doesn't matter whether they are relevant links or not
                        rsoup = BeautifulSoup(relevantContent)
                        allAnchorTags = rsoup.findAll("a")
                        for atag in allAnchorTags:
                            if atag.has_key("href"):
                                link = atag.get("href")
                                # Try to access it...
                                try:
                                    urllib2.urlopen(link)
                                    self.logger.write("Followed link %s"%link)
                                    self.successfulLinkVerifications.append(link)
                                except:
                                    continue
                    else: # content is a json data structure
                        jsonData = json.loads(content)
                        relevantContent = jsonData['result']['message'][0]['part'][0]['text']
                        rsoup = BeautifulSoup(relevantContent.encode("utf-8", "ignore"))
                        validationPattern = re.compile(r"validation", re.IGNORECASE)
                        allAnchorTags = rsoup.findAll("a")
                        for atag in allAnchorTags:
                            if atag.has_key("href"):
                                link = atag.get("href")
                                link = link.replace(r"\/", "/")
                                if not validationPattern.search(link): # No use trying to follow links that are not for account validation.
                                    continue
                                print "Trying to follow email link: " + link.encode("ascii", "ignore")
                                # Try to access it...
                                try:
                                    urllib2.urlopen(link)
                                    self.logger.write("Followed link %s"%link.encode("ascii", "ignore"))
                                    self.successfulLinkVerifications.append(link)
                                except:
                                    print "Could not follow email link %s - Error: %s"%(link.encode("ascii", "ignore"), sys.exc_info()[1].__str__())
                                    continue
            ret = self.mailbot.getNextPage()
            if not ret:
                break
            

    def handleStoryPosting(self, siteUrl, story, threadCtr, voteStoriesCount=None):
        configFile = r"config" + os.path.sep + "app.cfg"
        webop = SiteAccountOperator(configFile, siteUrl)
        userId, passwd = self.__class__.sitesCredsDict[siteUrl]
        print "Attempting to post to %s using username '%s' and password '%s'"%(siteUrl, userId, passwd)
        self.logger.write("Attempting to post to %s using username '%s' and password '%s'"%(siteUrl, userId, passwd))
        self.logger.write("Story Post Thread Id " + self.storyPostThreadsDict[threadCtr.__str__()].__str__() + " starting - URL: " + siteUrl)
        retval = webop.getLoginPage()
        tid = self.storyPostThreadsDict[threadCtr.__str__()]
        if retval:
            retval2 = webop.doLogin(userId, passwd)
            if retval2:
                storyTitle, storyUrl = webop.postStory(story, self.newsUrl, self.newsTags)
                if voteStoriesCount:
                    webop.castVote(voteStoriesCount)
                if storyUrl:
                    # Add to database here
                    self.addToDatabase(webop, userId, passwd, storyTitle, storyUrl)
                    self.storyPostThreadsDict[threadCtr.__str__()] = None
                    self.logger.write("Successfully posted story to %s - %s exiting..."%(siteUrl, tid.__str__()))
                    self.successfulStoryPosts.append(siteUrl)
                    return (tid)
        self.storyPostThreadsDict[threadCtr.__str__()] = None
        self.logger.write("Failed to post story to %s - %s exiting..."%(siteUrl, tid.__str__()))
        sys.stdout.flush()
        return (tid)


    def addToDatabase(self, webop, username, password, storyTitle, storyUrl):
        print "Adding database entry for the storyUrl %s"%storyUrl
        self.logger.write("Adding database entry for the storyUrl %s"%storyUrl)
        # The storyUrl needs to be stored in the database.
        try:
            sql = "insert into storypost (websiteUrl, registrationUrl, userId, password, storyPostedDate, storyTitle, storyUrl) values ('%s', '%s', '%s', '%s', now(), '%s', '%s')"%(webop.websiteUrl, webop.registrationUrl, username, password, storyTitle, storyUrl)
            #print "SQL: ", sql
            webop.dbconn.begin()
            webop.cursor.execute(sql)
            webop.dbconn.commit()
        except MySQLdb.Error, e:
            print "Transaction failed, rolling back. Error was:"
            print e.args
            webop.dbconn.rollback()
            

    def tidHasStopped(cls, tid):
        stoppedPattern = re.compile(r"Thread-\d+, stopped", re.IGNORECASE)
        if stoppedPattern.search(tid.__str__()):
            return True
        return False
    tidHasStopped = classmethod(tidHasStopped)
    

    def searchGoogle(self, searchString):
        sys.path.append(os.getcwd() + os.path.sep + r"api")
        from xgoogle.search import GoogleSearch, SearchError
        searchResults = []
        self.logger.write("Starting google search with search string '%s'..." % searchString)
        try:
            gs = GoogleSearch(searchString)
            gs.results_per_page = 100
            while True:
                results = gs.get_results()
                if not results:
                    break
                searchResults.extend(results)
        except SearchError, e:
            print "Google Search failed: %s" % e
            self.logger.write("Google Search failed: %s" % e)
            return None
        if searchResults.__len__() > 0:
            self.logger.write("Fetched results successfully. Starting to parse....")
            google_search_results_dumpdir = os.getcwd() + os.path.sep + "google_search_results"
            filesQueue = []
            websiteUrlPattern = re.compile(r"([\w\.]*[\w]+[\-\w]*\.)(\w{2,3})")
            ipAddressPattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
            httpPattern = re.compile(r"^http://")
            endSlashPattern = re.compile(r"/$")
            invalidDomainStrings = ['gif', 'jpg', 'png', 'bmp', 'css', 'js', 'htm', 'pdf', 'tif', 'txt', 'dat', 'php', 'asp', 'jar', 'cfm']
            # We don't want strings ending with any of the above sequence of characters as they are not domains, but possibly filenames...
            if not os.path.exists(google_search_results_dumpdir):
                os.makedirs(google_search_results_dumpdir)
            for res in searchResults:
                r_resp = urllib.urlopen(res.url)
                rand_str = int(time.time()).__str__()
                filename = "f_" + rand_str + ".html"
                f = open(google_search_results_dumpdir + os.path.sep + filename, "w")
                f.write(EmailBot._decodeGzippedContent(r_resp.read()))
                f.close()
                filesQueue.append(google_search_results_dumpdir + os.path.sep + filename)
            uniqueSitesDict = {}
            self.logger.write("Dumped website contents....")
            while filesQueue.__len__() > 0:
                file = filesQueue.pop()
                fr = open(file)
                contents = fr.read()
                fr.close()
                fsoup = BeautifulSoup(contents)
                # Get all anchor tags...
                allAnchorTags = fsoup.findAll("a")
                for anchor in allAnchorTags: # we will be looking for texts in the anchor tag that matches one of the patterns (websiteUrlPattern or ipAddressPattern)
                    anchorText = anchor.renderContents()
                    anchorText = anchorText.strip(" ")
                    websiteSearchResult = websiteUrlPattern.search(anchorText)
                    ipAddressSearchResult = ipAddressPattern.search(anchorText)
                    if ipAddressSearchResult:
                        siteUrl = ipAddressSearchResult.groups()[0]
                        if not uniqueSitesDict.has_key(siteUrl):
                            uniqueSitesDict[siteUrl] = 1
                    elif websiteSearchResult:
                        siteUrl1 = websiteSearchResult.groups()[0].lower()
                        siteUrl2 = websiteSearchResult.groups()[1].lower()
                        if siteUrl2 not in invalidDomainStrings:
                            siteUrl = siteUrl1 + siteUrl2
                            if not httpPattern.search(siteUrl):
                                siteUrl = "http://" + siteUrl
                            if not endSlashPattern.search(siteUrl):
                                siteUrl = siteUrl + "/"
                            if not uniqueSitesDict.has_key(siteUrl):
                                uniqueSitesDict[siteUrl] = 1
                    else:
                        pass
                # Unlink the file now...
                os.unlink(file)
            # Finally, return the list of keys of the unique sites dictionary...
            self.logger.write("Done! Retrieved %s websites."%uniqueSitesDict.keys().__len__().__str__())
            rand_str = int(time.time()).__str__()
            siteslistfile = "sites_" + rand_str + ".dat"
            self.logger.write("Dumping them into the file %s"%(google_search_results_dumpdir + os.path.sep + siteslistfile))
            fw = open(google_search_results_dumpdir + os.path.sep + siteslistfile, "w")
            fw.write("\n".join(uniqueSitesDict.keys()))
            fw.close()
            self.logger.write("Appending the list to 'sitesQueue'... ")
            for newsite in uniqueSitesDict.keys():
                self.sitesQueue.append(newsite)
            return (uniqueSitesDict.keys())
        else:
            self.logger.write("The google search did not return any results.")
            return ([])

        
    def runApp(self):
        self.enqueueStories()
        storiesCount = 0
        # First, handle all registrations...
        print "Attempting to register on all links..."
        threadCountReg = self.maxOperatorThreadsRegistrations
        sys.stdout.flush()
        threadCtr = 0
        sitesCtr = 1
        numSites = self.sitesQueue.__len__()
        sitesQueueBackup = []
        usernameQueueBackup = []
        self.__class__.sitesCredsDict = {}
        googleSearchTID = None
        if self.bgGoogleSearch:
            try:
                googleSearchTID = Thread(target=self.searchGoogle, args=(self.bgGoogleSearchKeywords, ))
                self.logger.write("Starting google search for keywords '%s' in a background thread - %s... "%(self.bgGoogleSearchKeywords, googleSearchTID.__str__()))
                googleSearchTID.start() # We need to 'join' this thread later (to avoid having runaway thread after the main script finishes)
            except:
                print "Failed to start google search thread. Error: " + sys.exc_info()[1].__str__()
                self.logger.write("Failed to start google search thread. Error: " + sys.exc_info()[1].__str__())
        for site in self.sitesQueue:
            sitesQueueBackup.append(site)
        for userId in self.usernameQueue:
            usernameQueueBackup.append(userId)
        while self.sitesQueue.__len__() > 0:
            siteUrl = self.sitesQueue.pop(0)
            if self.usernameQueue.__len__() > 0:
                self.userId = self.usernameQueue.pop(0)
            else:
                for userId in usernameQueueBackup:
                    self.usernameQueue.append(userId)
                self.userId = self.usernameQueue.pop(0)
            self.logger.write("Processing website (#%s): %s"%(sitesCtr.__str__(), siteUrl))
            sitesCtr += 1
            curThreadCount = [val for val in self.registrationThreadsDict.values() if val is not None].__len__()
            if curThreadCount < int(threadCountReg):
                self.logger.write("Number of threads: " + curThreadCount.__str__())
                tid = Thread(target=self.handleRegistration, args=(siteUrl, threadCtr))
                self.logger.write("Creating thread %s"%tid.__str__())
                self.registrationThreadsDict[threadCtr.__str__()] = tid
                threadCtr += 1
            else:
                for tkey in self.registrationThreadsDict.keys():
                    tid = self.registrationThreadsDict[tkey]
                    if tid and not tid.isAlive() and not self.__class__.tidHasStopped(tid):
                        try:
                            self.logger.write("Starting thread " + tid.__str__())
                            tid.start()
                        except:
                            self.logger.write("Could not start thread %s - Reason: %s"%(tid.__str__(), sys.exc_info()[1].__str__()))
            # If too many threads have been created, then call the oldest threads join method
            curThreadCount = [val for val in self.registrationThreadsDict.values() if val is not None].__len__()
            if curThreadCount >= int(threadCountReg):
                threadKeys = self.registrationThreadsDict.keys()
                threadKeys.sort(reverse=True)
                self.logger.write("Number of concurrent threads at this instant: " + curThreadCount.__str__())
                for key in threadKeys:
                    if self.registrationThreadsDict.has_key(key) and self.registrationThreadsDict[key] and self.registrationThreadsDict[key].isAlive():
                        self.registrationThreadsDict[key].join()
                        self.registrationThreadsDict[key] = None
                        sys.stdout.flush()
                        break
        self.logger.write("Successfully registered in %s of the %s websites listed"%(self.successfulRegistrations.__len__().__str__(), numSites.__str__()))
        sys.stdout.flush()
        # Next, verify all emailed links...
        print "Attempting to verify all emailed links..."
        self.logger.write("Attempting to verify all emailed links...")
        self.handleEmailLinkVerifications() 
        threadCountPost = self.maxOperatorThreadsStoryPost
        sys.stdout.flush()
        threadCtr = 0
        self.sitesQueue = []
        for site in sitesQueueBackup:
            self.sitesQueue.append(site)
        print "Number of sites to post to: " + self.sitesQueue.__len__().__str__()
        self.logger.write("Number of sites to post to: " + self.sitesQueue.__len__().__str__())
        while self.sitesQueue.__len__() > 0:
            siteUrl = self.sitesQueue.pop(0)
            if not siteUrl in self.successfulRegistrations: # No use trying to log in to a site on which our registration had failed.
                print "Registration was not successful for %s. Skipping it ...."%siteUrl
                continue
            curThreadCount = [val for val in self.storyPostThreadsDict.values() if val is not None].__len__()
            if curThreadCount < int(threadCountPost):
                self.logger.write("Number of threads: " + curThreadCount.__str__())
                story = self.storyQueue.pop(0)
                if not self.usrVotePrev:
                    tid = Thread(target=self.handleStoryPosting, args=(siteUrl, story, threadCtr))
                else:
                    tid = Thread(target=self.handleStoryPosting, args=(siteUrl, story, threadCtr, self.setVoteStoriesCount))
                self.storyPostThreadsDict[threadCtr.__str__()] = tid
                threadCtr += 1
            else:
                for tkey in self.storyPostThreadsDict.keys():
                    tid = self.storyPostThreadsDict[tkey]
                    if tid and not tid.isAlive() and not self.__class__.tidHasStopped(tid):
                        try:
                            tid.start()
                            self.logger.write("Starting thread " + tid.__str__())
                        except:
                            self.logger.write("Could not start thread %s -- Reason: %s"%(tid.__str__(), sys.exc_info()[1].__str__()))
            # If too many threads have been created, then call the oldest threads join method
            curThreadCount = [val for val in self.storyPostThreadsDict.values() if val is not None].__len__()
            if curThreadCount >= int(threadCountPost) or self.storyQueue.__len__() == 0:
                threadKeys = self.storyPostThreadsDict.keys()
                threadKeys.sort(reverse=True)
                for key in threadKeys:
                    if self.storyPostThreadsDict[key] and self.storyPostThreadsDict[key].isAlive():
                        self.storyPostThreadsDict[key].join()
                        self.storyPostThreadsDict[key] = None
                        sys.stdout.flush()
                        break
        self.logger.write("Successfully posted to %s websites"%self.successfulStoryPosts.__len__().__str__())
        # Check if we started google search and if the thread is still running in the background. If so, inform the user accordingly.
        if googleSearchTID and googleSearchTID.isAlive():
            print "A background thread performing Google search (for keywords '%s' is still running... "%self.bgGoogleSearchKeywords
            print "Click the 'Exit' button to stop the search and exit the application. "
            print "Do nothing to complete the search process. Once the search is complete, the application will exit by itself."
            googleSearchTID.join()
        sys.stdout.flush()
        return (self.successfulStoryPosts)



"""
This is a wrapper implementing the GUI for the above class "RunManager".
"""
class GuiWrapper(RunManager):

    def __init__(self):
        self.usrSpinableContent = ""
        self.usrWebsites = ""
        self.usrStoryTitle = ""
        self.usrStoryUrl = ""
        self.usrStoryTags = ""
        self.usrRegUsername = ""
        self.usrRegPassword = ""
        self.usrEmailId = ""
        self.usrEmailPasswd = ""
        self.usrSearchGoogleBackground = False
        
        self.root = Tk()
        self.root.title("Post stories automatically to PLIGG based websites")
        
        self.storyInfoFrame = LabelFrame(self.root, text="Story Info")
        self.storyInfoFrame["width"] = self.root["width"]
        self.storyInfoFrame.grid_propagate(0)
        self.storyInfoFrame.pack()

        self.storyFrameOne = Frame(self.storyInfoFrame)
        self.storyFrameOne.pack()
        self.storyUrlLabel = Label(self.storyFrameOne, text="Enter Story URL:")
        self.storyUrlLabel.pack(side=LEFT)
        self.storyUrlEntry = Entry(self.storyFrameOne, width=70)
        self.storyUrlEntry.pack(expand=1, fill=Y, side=LEFT)

        self.storyFrameTwo = Frame(self.storyInfoFrame)
        self.storyFrameTwo.pack()
        self.storyTitleLabel = Label(self.storyFrameTwo, text="Enter Story Title:")
        self.storyTitleLabel.pack(side=LEFT)
        self.storyTitleEntry = Entry(self.storyFrameTwo, width=70)
        self.storyTitleEntry.pack(expand=1, fill=Y, side=LEFT)

        self.storyFrameThree = Frame(self.storyInfoFrame)
        self.storyFrameThree.pack()
        self.storyTagsLabel = Label(self.storyFrameThree, text="Enter Story Tags:")
        self.storyTagsLabel.pack(side=LEFT)
        self.storyTagsEntry = Entry(self.storyFrameThree, width=70)
        self.storyTagsEntry.pack(expand=1, fill=Y, side=LEFT)

        self.spinContentLabel = Label(self.storyInfoFrame, text="Enter Story Content\n(Spinable Text):")
        self.spinContentLabel.pack(side=LEFT)
        self.spinContentText = Text(self.storyInfoFrame, state='normal', undo=True, width=60, height=10, wrap=WORD)
        self.ySpinContentScroll = Scrollbar (self.storyInfoFrame, orient=VERTICAL, command=self.spinContentText.yview)
        self.spinContentText.configure(yscrollcommand=self.ySpinContentScroll.set)
        self.spinContentText.pack(expand=1, fill=Y, side=LEFT)
        self.ySpinContentScroll.pack(fill=Y, side=LEFT)

        self.pliggSitesFrame = LabelFrame(self.root, text="Input Data")
        self.pliggSitesFrame["width"] = self.root["width"]
        self.pliggSitesFrame.grid_propagate(0)
        self.pliggSitesFrame.pack()

        self.pliggSitesLabel = Label(self.pliggSitesFrame, text="Enter Website URLs:")
        self.pliggSitesLabel.pack(side=LEFT)
        self.pliggSitesText = Text(self.pliggSitesFrame, state='normal', undo=True, width=60, height=10, wrap=WORD)
        self.yPliggSitesScroll = Scrollbar (self.pliggSitesFrame, orient=VERTICAL, command=self.pliggSitesText.yview)
        self.pliggSitesText.configure(yscrollcommand=self.yPliggSitesScroll.set)
        self.pliggSitesText.pack(expand=1, fill=Y, side=LEFT)
        self.yPliggSitesScroll.pack(fill=Y, side=LEFT)

        self.registrationInfoFrame = LabelFrame(self.root, text="Registration Data")
        self.registrationInfoFrame["width"] = self.root["width"]
        self.registrationInfoFrame.grid_propagate(0)
        self.registrationInfoFrame.pack(expand=1)

        self.credsFrame = Frame(self.registrationInfoFrame)
        self.credsFrame.pack()
        self.usernameLabel = Label(self.credsFrame, text="Username:")
        self.usernameLabel.pack(side=LEFT, expand=1)
        self.usernameEntry = Entry(self.credsFrame, width=25)
        self.usernameEntry.pack(expand=1, fill=Y, side=LEFT)
        self.emptyLabelOne = Label(self.credsFrame, text="     ")
        self.emptyLabelOne.pack(side=LEFT)
        self.passwordLabel = Label(self.credsFrame, text="Password:")
        self.passwordLabel.pack(side=LEFT)
        self.passwordEntry = Entry(self.credsFrame, width=25)
        self.passwordEntry.pack(expand=1, fill=Y, side=LEFT)

        self.emailFrame = Frame(self.registrationInfoFrame)
        self.emailFrame.pack()
        self.emailIdLabel = Label(self.emailFrame, text="Email ID:")
        self.emailIdLabel.pack(side=LEFT)
        self.emailIdEntry = Entry(self.emailFrame, width=23)
        self.emailIdEntry.pack(expand=1, fill=Y, side=LEFT)
        self.emptyLabelTwo = Label(self.emailFrame, text="     ")
        self.emptyLabelTwo.pack(side=LEFT)
        self.emailPasswdLabel = Label(self.emailFrame, text="Email Password:")
        self.emailPasswdLabel.pack(side=LEFT)
        self.emailPasswdEntry = Entry(self.emailFrame, width=23, show='*')
        self.emailPasswdEntry.pack(expand=1, fill=Y, side=LEFT)

        self.runOptionsFrame = Frame(self.root)
        self.runOptionsFrame["width"] = self.root["width"]
        self.runOptionsFrame.grid_propagate(0)
        self.runOptionsFrame.pack(expand=1)

        self.voteActionTracker = IntVar()
        self.googleSearchActionTracker = IntVar()
        self.votePreviousProfilesCheckButton = Checkbutton(self.runOptionsFrame, text="Vote On Previous Posts", command=self.setVotePrevFlag, justify=LEFT, variable=self.voteActionTracker)
        self.votePreviousProfilesCheckButton.pack(side=LEFT)
        self.voteOnStoriesCountEntry = Entry(self.runOptionsFrame, width=10, state=DISABLED)
        self.voteOnStoriesCountEntry.pack(side=LEFT)
        self.emptyLabelThree = Label(self.runOptionsFrame, text="     ")
        self.emptyLabelThree.pack(side=LEFT)
        self.backgroundGoogleSearchCheckButton = Checkbutton(self.runOptionsFrame, text="Search Google in background", justify=LEFT, command=self.setSearchGoogleFlag, variable=self.googleSearchActionTracker)
        self.backgroundGoogleSearchCheckButton.pack(side=LEFT)
        self.backgroundGoogleSearchEntry = Entry(self.runOptionsFrame, width=10, state=DISABLED)
        self.backgroundGoogleSearchEntry.pack(side=LEFT)
        #self.addGoogledSitesCheckButton = Checkbutton(self.runOptionsFrame, text="Process Now", justify=LEFT, variable=self.googleSearchProcessNow)

        self.actionsFrame = Frame(self.root)
        self.actionsFrame.pack()
        self.runButton = Button(self.actionsFrame, text="Run App", command=self.startApp, width=15)
        self.runButton.pack(side=LEFT)
        self.exitButton = Button(self.actionsFrame, text="Exit App", command=self.root.quit, width=15)
        self.exitButton.pack(side=LEFT)


    def _getDataFromUser(self):
        self.usrSpinableContent = self.spinContentText.get("1.0", END)
        self.usrWebsites = self.pliggSitesText.get("1.0", END)
        self.usrStoryTitle = self.storyTitleEntry.get()
        self.usrStoryUrl = self.storyUrlEntry.get()
        self.usrStoryTags = self.storyTagsEntry.get()
        self.usrRegUsername = self.usernameEntry.get()
        self.usrRegPassword = self.passwordEntry.get()
        self.usrEmailId = self.emailIdEntry.get()
        self.usrEmailPasswd = self.emailPasswdEntry.get()
        self.usrRegUsernameList = []
        spinCharPattern = re.compile(r"|")
        if spinCharPattern.search(self.usrRegUsername): # username is spinable
            self.usrRegUsernameList = self.usrRegUsername.split("|")
        else:
            self.usrRegUsernameList.append(self.usrRegUsername)
        for i in range(self.usrRegUsernameList.__len__() - 1):
            self.usrRegUsernameList[i] = self.usrRegUsernameList[i].strip(" ").rstrip(" ")
        if self.voteActionTracker.get() == 1:
            self.usrVotePrev = True
            self.setVoteStoriesCount = self.voteOnStoriesCountEntry.get()
        if self.googleSearchActionTracker.get() == 1:
            self.bgGoogleSearch = True
            self.bgGoogleSearchKeywords = self.backgroundGoogleSearchEntry.get()

    def setVotePrevFlag(self):
        if self.voteActionTracker.get():
            # Configure the text field in the widget to NORMAL state, and get the number of stories (latest first) to vote
            self.voteOnStoriesCountEntry.configure(state=NORMAL)
        else:
            # Configure the text field to state=DISABLED
            self.voteOnStoriesCountEntry.configure(state=DISABLED)

    def setSearchGoogleFlag(self):
        if self.googleSearchActionTracker.get():
            self.backgroundGoogleSearchEntry.configure(state=NORMAL)
        else:
            self.backgroundGoogleSearchEntry.configure(state=DISABLED)
        

    def startApp(self):
        super(GuiWrapper, self).__init__()
        self._getDataFromUser()
        self.getStoryParams(self.usrSpinableContent, self.usrStoryUrl, self.usrStoryTags)
        self.getRegistrationParams(self.usrRegUsernameList, self.usrRegPassword, self.usrEmailId, self.usrEmailPasswd)
        self.createSitesQueue(self.usrWebsites)
        self.runApp()


if __name__ == "__main__":
    gr = GuiWrapper()
    gr.root.mainloop()
    gr.root.bell()
    



