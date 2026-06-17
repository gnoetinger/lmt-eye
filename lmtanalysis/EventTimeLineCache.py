'''
Created on 25 sept. 2018

@author: Fab
'''
import logging

from lmtanalysis.Event import EventTimeLine

eventCacheDico_={}
eventCacheEnable_ = True

def disableEventTimeLineCache():
    ''' If you are using a computer with small amount of RAM, it might be better to disable cache '''
    eventCacheDico_.clear()
    global eventCacheEnable_
    eventCacheEnable_ = False
    logging.info( "Cache event is disabled" )
    
    
def EventTimeLineCached( connection, file, eventName, idA=None, idB=None, idC=None, idD = None, minFrame=None, maxFrame=None, loadEventIndependently=False ):
            
    global eventCacheDico_
    
    if eventCacheEnable_ == True:
    
        logging.debug( f"Cache debug: {connection}, {file}, {eventName}, ids: {idA}, {idB}, {idC}, {idD}, frames: {minFrame}, {maxFrame}, loadEventIndependently: {loadEventIndependently}" )
        
        
        if (file, eventName, idA, idB, idC, idD, minFrame, maxFrame, loadEventIndependently ) in eventCacheDico_: 
            eventTimeLine = eventCacheDico_[ file, eventName, idA, idB, idC, idD, minFrame, maxFrame, loadEventIndependently ]
            logging.debug( f"{eventName} Id({idA},{idB},{idC},{idD}) Loaded from cache ({len(eventTimeLine.eventList)} records.)" )
            return eventTimeLine

        
    eventTimeLine = EventTimeLine( connection, eventName , idA = idA, idB = idB, idC = idC, idD = idD, minFrame = minFrame, maxFrame = maxFrame , loadEventIndependently = loadEventIndependently )
    
    if eventCacheEnable_ == True:
        logging.debug( "Caching eventTimeLine")
        eventCacheDico_[ file, eventName, idA, idB, idC, idD, minFrame, maxFrame, loadEventIndependently ] = eventTimeLine
    else:
        logging.debug( "Loading event from base (Cache event disabled)")
    
    return eventTimeLine
        
def flushEventTimeLineCache():
    eventCacheDico_.clear()