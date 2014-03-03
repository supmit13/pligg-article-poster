import os, sys, re, time
import urllib2, urllib
sys.path.append(os.getcwd() + os.path.sep + "handlers")
from bots.EmailBot import EmailBot
from BeautifulSoup import BeautifulSoup


def searchGoogle(keywords):
    sys.path.append(os.getcwd() + os.path.sep + r"api")
    from xgoogle.search import GoogleSearch, SearchError
    searchResults = []
    try:
        gs = GoogleSearch(keywords)
        gs.results_per_page = 100
        while True:
            results = gs.get_results()
            if not results:
                break
            searchResults.extend(results)
    except SearchError, e:
        print "Search failed: %s" % e
    if searchResults.__len__() > 0:
        google_search_results_dumpdir = os.getcwd() + os.path.sep + "google_search_results"
        filesQueue = []
        websiteUrlPattern = re.compile(r"([\w\.]*[\w]+[\-\w]*\.)(\w{2,3})")
        ipAddressPattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
        invalidDomainStrings = ['gif', 'jpg', 'png', 'bmp', 'css', 'js', 'htm', 'pdf', 'tif', 'txt', 'dat']
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
                    siteUrl = ipAddressSearchResult.groups()[0].lower()
                    if not uniqueSitesDict.has_key(siteUrl):
                        uniqueSitesDict[siteUrl] = 1
                elif websiteSearchResult:
                    siteUrl1 = websiteSearchResult.groups()[0].lower()
                    siteUrl2 = websiteSearchResult.groups()[1].lower()
                    if siteUrl2 not in invalidDomainStrings:
                        siteUrl = siteUrl1 + siteUrl2
                        if not uniqueSitesDict.has_key(siteUrl):
                            uniqueSitesDict[siteUrl] = 1
                else:
                    pass
            # Unlink the file now...
            os.unlink(file)
        # Finally, return the list of keys of the unique sites dictionary...
        return (uniqueSitesDict.keys())
    else:
        return (None)
                    
            

if __name__ == "__main__":
    sitesList = searchGoogle("Pligg websites")
    if sitesList:
        for site in sitesList:
            print site
        print "Retrieved %s sites."%str(sitesList.__len__())
    else:
        print "Could not fetch websites list..."



