import logging
import os
from datetime import datetime
import azure.functions as func
import json
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import (
    TextAnalyticsClient,
    ExtractSummaryAction
)
from azure.cosmos import CosmosClient, PartitionKey


def analyze_doc(doc_id, cs_doc):

    items = []
    document = None
    d = {}
    
    try:
        COSMOSURI = os.getenv("COSMOSURI") 
        logging.warning("COSMOSURI")
        COSMOSKEY = os.getenv("COSMOSKEY") 
        COGSERVKEY = os.getenv("COGSERVKEY") 
        COGSERVENDPOINT = os.getenv("COGSERVENDPOINT")

        client = CosmosClient(url=COSMOSURI, credential=COSMOSKEY)
        db = client.get_database_client(database="scdb")
        container = db.get_container_client("documents")

        QUERY = "SELECT * FROM documents p WHERE p.categoryId = @categoryId AND p.id = @id"
        CATEGORYID = "61dba35b-4f02-45c5-b648-c6badc0cbd79"
        params = [dict(name="@categoryId", value=CATEGORYID), dict(name="@id", value=doc_id)]
        items = container.query_items(query=QUERY, parameters=params, enable_cross_partition_query=False)


    except Exception as e:                       
        return "something wrong with db connection " 

    try:
        document = items.next()
        d["text"]  = document['text']

    except Exception as e:

        try:
            text_analytics_client = TextAnalyticsClient(endpoint=COGSERVENDPOINT, 
                                                    credential=AzureKeyCredential(COGSERVKEY))
            poller = text_analytics_client.begin_analyze_actions([cs_doc],actions=[ExtractSummaryAction()])                                                    
        except:
            return "analyze error"                                                    
                                                    
        
        document_results = poller.result()

        for summary_results in document_results:
            for result in summary_results:
                if result.kind == "ExtractiveSummarization":
                    d["text"] = " ".join([sentence.text for sentence in result.sentences])
                elif result.is_error is True:
                    print("...Is an error with code '{}' and message '{}'".format(
                        result.code, result.message
                    ))
    return d



## Perform an operation on a record
def transform_value(value):
    try:
        recordId = value['recordId']
    except AssertionError  as error:
        return None

    # Validate the inputs
    try:         
        assert ('data' in value), "'data' field is required."
        data = value['data']        
        assert ('content' in data), "'content' field is required in 'data' object."
        assert ('id' in data), "'id' field is required in 'data' object."
        
    except AssertionError  as error:
        return (
            {
            "recordId": recordId,
            "errors": [ { "message": "Error:" + error.args[0] }   ]       
            })

    try:                
        concatenated_string = analyze_doc(value['data']['id'], value['data']['content'])
        # Here you could do something more interesting with the inputs

    except:
        return (
            {
            "recordId": recordId,
            "errors": [ { "message": "Could not complete operation for record." }   ]       
            })

    return ({
            "recordId": recordId,
            "data": concatenated_string
            })



def compose_response(json_data):
    values = json.loads(json_data)['values']
    
    # Prepare the Output before the loop
    results = {}
    results["values"] = []
    
    for value in values:
        output_record = transform_value(value)
        if output_record != None:
            results["values"].append(output_record)

    return json.dumps(results, ensure_ascii=False)

    

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        body = json.dumps(req.get_json())
    except ValueError:
        return func.HttpResponse(
             "Invalid body",
             status_code=400
        )
    
    if body:
        result = compose_response(body)
        return func.HttpResponse(result, mimetype="application/json")
    else:
        return func.HttpResponse(
             "Invalid body",
             status_code=400
        )
