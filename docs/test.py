import os, sys, re

"""
f = open(r"C:\work\projects\Odesk\PliggStoryPoster\pligg.txt")
allLines = f.readlines()
f.close()

urlpattern = re.compile(r"^(http://[^/]+/).*$")
modLines = []
for line in allLines:
    urlsearch = urlpattern.search(line)
    if urlsearch:
        modline = urlsearch.groups()[0]
        modLines.append(modline)
lineschunk = "\n".join(modLines)
ff = open(r"C:\work\projects\Odesk\PliggStoryPoster\pligg2.txt", "w")
ff.write(lineschunk)
ff.close()
"""
"""
import urllib, urllib2
from BeautifulSoup import BeautifulSoup
sys.path.append(r"C:\work\projects\Odesk\PliggStoryPoster\api")
"""

import os, sys
import urllib2, urllib
from BeautifulSoup import BeautifulSoup
sys.path.append("." + os.path.sep + "api")
from xgoogle.search import GoogleSearch, SearchError

def doGoogleSearch(searchString):
    searchResults = []
    try:
        gs = GoogleSearch(searchString)
        gs.results_per_page = 100
        while True:
            results = gs.get_results()
            if not results:
                break
            searchResults.extend(results)
    except SearchError, e:
        print "Search failed: %s" % e
    return(searchResults)

"""
def doGoogleSearch(keywords):
    searchUrl = "http://www.google.com/"
    searchResponse = urllib2.urlopen(searchUrl)
    searchPageContent = searchResponse.read()
    soup = BeautifulSoup(searchPageContent)
    searchForm = soup.find("form", {'action' : '/search'})
    formContents = searchForm.renderContents()
    fsoup = BeautifulSoup(formContents)
    formElements = fsoup.findAll("input")
    searchQueryString = ""
    for elem in formElements:
        if elem.has_key("name") and elem.get("name") == 'q':
            searchQueryString += "q=" + "%2c".join(keywords) + "&"
        elif elem.has_key("name") and elem.get("name") == 'btnI':
            continue
        else:
            if elem.has_key("name"):
                searchQueryString += elem['name'] + "=" + elem.get("value", "") + "&"
            elif elem.has_key("id"):
                searchQueryString += elem['id'] + "=" + elem.get("value", "") + "&"
            else:
                pass
    searchQueryString = searchQueryString.replace(" ", "+")
    searchQueryString = searchUrl[:-1] + searchForm["action"] + "?" + searchQueryString[:-1]
    print searchQueryString
    try:
        searchResponse2 = urllib2.urlopen(searchQueryString)
    except:
        print "Error fetching search results"
        sys.exit()
    searchResponseContent2 = searchResponse2.read()
    return (searchResponseContent2)
"""
def encode_multipart_formdata(fields):
    Return (content_type, body) ready for httplib.HTTP instance
    """
    BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
    CRLF = '\r\n'
    L = []
    for (key, value) in fields.iteritems():
        L.append('--' + BOUNDARY)
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be uploaded as files
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body

if __name__ == "__main__":
    postData = {'category' : '1',
                'bodytext' : 'An enormous number of pounds together with  dollars are  offered this winter for the reason that  online casinos prepare to venture to war over your enrollment . Listen up %3B this document  describes  insights on how  avid gamers can take benefit of Christmas online slots and also UK slots bonuses on multilple web sites  within the  annual vacations . The big casino brands even roll-out  their personal Christmas related slots games that come with  remarkable  images  together with bonuses for the festive mood. %0A%0AThose that love games as well as other online entertainment routines  are usually in for a great  The holiday season %2C because it is  believed  that over 1.2 billion dollars are definitely  expended by casinos upon free slots in the course of the festivities. November and December are definitely the  very best  moments  to register to an online casino web site the  registration bonuses usually are huge with no deposit were required to  have them . \n',
                'randkey' : '8742322',
                'recaptcha_response_field' : 'mcric r4awful',
                'tags' : 'screen scraping, automation',
                'url' : 'http://www.vnsinfo.com.au/ecommerce-web-design-sydney.html',
                'title' : 'Gain several a large amount with internet slots',
                'text_num' : '0',
                'recaptcha_challenge_field' : '03AHJ_VuvHjHUwRjcW4yUZrs5V2GxmlqVilmz-My9RakGR13V3uiQDu1Wbx6VBBbGwV0T2PjJchiLDIJ31k2I9WW4ctWr_NzTkrTvBAVBDz3f8gCwQ8kWxGSRFLCMB53NbXkxsQRlT-2JtAcLR9zSs--0XnTsJTyNn8Q',
                'phase' : '2',
                'trackback' : '',
                'spelling' : 'Check spelling',
                'id' : '209904'
            }
    content_type, body = encode_multipart_formdata(postData)
    print body
    """
    searchTerms = 'pligg websites'
    results = doGoogleSearch(searchTerms)
    f = open(r"C:\work\projects\Odesk\PliggStoryPoster\googleSearch.html", "w")
    for res in results:
        f.write(res.title.encode("utf8"))
        f.write(res.desc.encode("utf8"))
        f.write(res.url.encode("utf8"))
        f.write("\n=============================================\n")
    f.close()
    """
"""

from PyQt4 import QtGui


def main():
    app = QtGui.QApplication(sys.argv)
    w = QtGui.QWidget()
    w.resize(250, 150)
    w.move(300, 300)
    w.setWindowTitle('Simple')
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
"""
