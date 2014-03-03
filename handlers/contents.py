import os, sys, re, time
from BeautifulSoup import BeautifulSoup
import csv
from Queue import Queue
import random


"""
Story class' objects will be used by the other entities involved in this task.
"""
class Story(object):
    def __init__(self, title="", contentBlocks=[], author="", publisher=""):
        self.title = title
        self.author = author
        self.preface = ""
        self.contents = ". ".join(contentBlocks)
        self.contentLength = len(self.contents)
        self.publisher = publisher

    def __getattr__(self, attrname):
        if attrname == "getPublisher":
            return (self.publisher)
        elif attrname == "getAuthor":
            return (self.author)
        elif attrname == "getTitle":
            return (self.title)
        elif attrname == "getContents":
            return (self.contents)
        elif attrname == "getContentLength":
            return (self.contentLength)
        else:
            print "Undefined method or attribute"
            return (None)

    def setPublisher(self, pub):
        self.publisher = pub

    def setPreface(self, pref):
        self.preface = pref

    def setAuthor(self, auth):
        self.author = auth

    def setTitle(self, tit):
        self.title = tit

    def setContents(self, contB):
        if type(contB) == list:
            self.contents = ". ".join(contB)
        else:
            self.contents = contB
        self.contentLength = len(self.contents)

    def __str__(self):
        strStory = self.getTitle + "\n\n"
        strStory += "A Story by " + self.getAuthor + "\n\n"
        strStory += self.getContents
        return strStory

    __repr__ = __str__


"""
This class is used to create a 'ContentQueue' object where a 'ContentSpinner' object will dump the generated stories one by one.
The 'ContentQueue' object will also be used by the 'DataPostOperator' object, which will pick up stories from the queue and try
to post them to one of the PLIGG websites. The ContentQueue object may be created in the __init__.py file in this package.
"""
class ContentQueue(Queue):
    pass


"""
This class handles the story creation with the text. It is aided by the module named 'random' which helps us in generating
random values between 0 and 1 which we use to pick up the sections of the stories randomly. It dumps the generated story
object in a ContentQueue object, which is used by the 'Web' object. The 'SiteAccountOperator' object picks up
stories from the queue (ContentQueue object) where 'Story' objects were dumped.
"""
class ContentSpinner(object):
    validBlockNames = ['Title', 'Body', 'Preface', 'TOC', 'Forward', 'Index']
    emptyStringPattern = re.compile(r"^\s*$")
    blockHeaderPattern = re.compile(r"^(\w+):\s*(.*)$", re.IGNORECASE)

    def __init__(self, spinText):
        self.spinText = spinText
        self.storyList = [] # This will contain a list of story objects that has been created during a session but is yet to be processed.
        self.spinContents = {}
        # Split the text and parse it to populate the contents dict.
        textLines = self.spinText.split("\n")
        lastCtr = 0
        for line in textLines:
            if self.__class__.emptyStringPattern.search(line):
                continue
            line = line.replace("{", "}")
            blockHeaderSearch = self.__class__.blockHeaderPattern.search(line)
            if blockHeaderSearch:
                header = blockHeaderSearch.groups()[0].upper()
                text = blockHeaderSearch.groups()[1]
                textParts = text.split("}")
                textList = []
                for tpart in textParts:
                    tlist = tpart.split("|")
                    if tlist[0].__len__() == 0:
                        continue
                    tlist[0] = tlist[0].strip(" ")
                    textList.append(tlist)
                if not self.spinContents.has_key(header):
                    self.spinContents[header] = textList
                else:
                    if type(self.spinContents[header]) == list:
                        prevList = self.spinContents[header]
                        self.spinContents[header] = { '000' : prevList, '001' : textList }
                        lastCtr = 1
                    else:
                        lastCtr += 1
                        strLastCtr = lastCtr.__str__()
                        if len(strLastCtr) < 3:
                            zeroPrefix = "0"
                            for i in range(len(strLastCtr), 3):
                                strLastCtr = zeroPrefix + strLastCtr
                        self.spinContents[header][strLastCtr] = textList
            else:
                pass # If a line has no block name, we just ignore it.


    def generateStory(self, auth="", pub=""):
        if len(self.spinContents.keys()) == 0:
            print "spinContents is empty. Can't generate stories."
            return (self.storyList)
        if not self.spinContents.has_key("TITLE"):
            print "No title found in the spin contents. Can't proceed."
            return None
        titlesList = self.spinContents["TITLE"]
        stitle = ""
        for titleBits in titlesList:
            titleBitsLen = len(titleBits)
            randNum = int(random.random() * titleBitsLen)
            stitle += titleBits[randNum] + " "
        stitle = stitle.replace("{", "")
        story = Story(stitle)
        spreface = ""
        if not self.spinContents.has_key("PREFACE"):
            pass
            #print "No preface found in the spin contents."
        else:
            prefaceList = self.spinContents["PREFACE"]
            for prefaceBits in prefaceList:
                prefaceBitsLen = len(prefaceBits)
                randNum = int(random.random() * prefaceBitsLen)
                spreface += prefaceBits[randNum]
            story.setPreface(spreface)
        sbody = ""
        if not self.spinContents.has_key("BODY"):
            print "No body found in the spin contents."
        else:
            bodyData = self.spinContents['BODY']
            if type(bodyData) == dict:
                sortedBodyKeys = bodyData.keys()
                sortedBodyKeys.sort()
                for bkey in sortedBodyKeys:
                    bodyList = bodyData[bkey]
                    for bodyBits in bodyList:
                        bodyBitsLen = len(bodyBits)
                        randNum = int(random.random() * bodyBitsLen)
                        sbody += bodyBits[randNum] + " "
                    sbody += "\n\n"
            else:
                for bodyBits in bodyData:
                    bodyBitsLen = len(bodyBits)
                    randNum = int(random.random() * bodyBitsLen)
                    sbody += bodyBits[randNum] + " "
            story.setContents(sbody)
        story.setAuthor(auth)
        story.setPublisher(pub)
        self.storyList.append(story)
        return(story)
            
    """
    ContentQueue is a Queue.Queue() object
    """
    def putStoriesInQueue(self, ContentQueue):
        for story in self.storyList:
            ContentQueue.put(story)
            





if __name__ == "__main__":
    s = Story("hello", ['hello', 'world'], "me", "myself")
    print s.getAuthor
    c= ContentSpinner(r"C:\work\projects\Odesk\PliggStoryPoster\docs\sampleContent.txt.txt")
    #for ck in c.spinContents.keys():
    #    print ck, " ====== ", c.spinContents[ck]
    print "==============================================================================================="
    s = c.generateStory("me", "myself")
    print s


