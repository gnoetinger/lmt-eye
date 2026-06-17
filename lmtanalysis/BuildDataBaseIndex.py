'''
Created on 6 sept. 2017

@author: Fab
'''
import logging
from lmtanalysis.TaskLogger import TaskLogger

def getNumberOfIndexOfDatabase( connection ):
    c = connection.cursor()
            
    query = "select type, name, tbl_name, sql FROM sqlite_master WHERE type='index'";
    c.execute( query )
    rows = c.fetchall()
    nbIndex = len( rows )
    logging.debug( f"Number of index in lmtanalysis: {nbIndex}" )
    return nbIndex

def executeLog( cursor, query):
    try:
        logging.debug( query )
        cursor.execute( query )
    except Exception as e:
        logging.debug (e)
    

def buildDataBaseIndex( connection , force=False):

    logging.info( "Creating lmtanalysis indexes...")

    c = connection.cursor()            

    '''
    if ( force == False ):
        if( getNumberOfIndexOfDatabase( connection ) > 0 ):
            logging.debug( "Index already exists (maybe not all)... no re-indexing. Use buildDataBaseIndex force parameter to force index build.")
            return
    '''
     
    executeLog( c , "CREATE INDEX `animalIndex` ON `ANIMAL` (`ID` );" )     

    executeLog( c , "CREATE INDEX `detectionIndex` ON `DETECTION` (`ID` ASC,`FRAMENUMBER` ASC);" )     
        
    executeLog( c , "CREATE INDEX `detetIdIndex` ON `DETECTION` (`ID` ASC);" )     
        
    executeLog( c , "CREATE INDEX `detframenumberIndex` ON `DETECTION` (`FRAMENUMBER` ASC);" )     
        
    executeLog( c , "CREATE INDEX `eventEndFrameIndex` ON `EVENT` (`ENDFRAME` ASC);" )     
        
    executeLog( c , "CREATE INDEX `eventIndex` ON `EVENT` (`ID` ASC,`STARTFRAME` ASC,`ENDFRAME` ASC);" )     

    executeLog( c , "CREATE INDEX `eventStartFrameIndex` ON `EVENT` (`STARTFRAME` ASC);" )     
        
    executeLog( c , "CREATE INDEX `eventstartendIndex` ON `EVENT` (`STARTFRAME` ASC,`ENDFRAME` ASC);" )     
        
    executeLog( c , "CREATE INDEX `indexeventidIndex` ON `EVENT` (`ID` ASC);" )     
    
    executeLog( c , "CREATE INDEX 'detectionFastLoadXYIndex' ON 'DETECTION' ('ANIMALID' ,'FRAMENUMBER' ASC,'MASS_X' ,'MASS_Y' );" )
    
    
    # log process
    t = TaskLogger( connection )
    t.addLog( "Build DataBase Index" )

        


