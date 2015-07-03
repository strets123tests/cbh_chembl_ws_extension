
from django.conf import settings
import elasticsearch

import time
try:
    ES_PREFIX = settings.ES_PREFIX
except AttributeError:
    ES_PREFIX = "dev"
ES_MAIN_INDEX_NAME = "chemreg_chemical_index"

def get_temp_index_name(request, multi_batch_id):
    index_name = "%s__temp_multi_batch__%s__%s" % (ES_PREFIX, request.session.session_key, str(multi_batch_id))
    print(index_name)
    return index_name
    #return "%s__temp_multi_batch__%s__%s" % (ES_PREFIX, request.session.session_key, str(multi_batch_id))

def get_main_index_name():
    return "%s__%s" % (ES_PREFIX, ES_MAIN_INDEX_NAME)

def delete_index(index_name):
    es = elasticsearch.Elasticsearch()
    return es.indices.delete(index_name)


def get(index_name, es_request_body, bundledata):
    es = elasticsearch.Elasticsearch()
    result = es.search(index_name, body=es_request_body)
    data = [res["_source"] for res in result["hits"]["hits"]]
    bundledata["meta"] = {"totalCount" : result["hits"]["total"]}
    bundledata["objects"] = data
    return bundledata

def get_autocomplete(projects, search_term, field, custom_fields=None, single_field=None):
    es = elasticsearch.Elasticsearch()
    project_terms = []
    print(single_field)
    search_regex = '.*%s.*|.*%s.*|.*%s.*|.*%s.*' % (search_term.title(), search_term, search_term.upper(), search_term.lower())
    field_to_search = '%s.raw' % (field)
    for proj in projects:
      project_name = '/%s/cbh_projects/%d' % (settings.WEBSERVICES_NAME, proj)
      project_terms.append( {'term': { 'project.raw': project_name } } )

    must_list = [{'bool': {
                    'should': project_terms,
                },}]
    if search_term and custom_fields:
        must_list.append({'bool': {
                    'should': [
                         {'prefix': { 'custom_field_list.searchable_name.raw':  search_term.lower() } },
                          {'prefix': { 'custom_field_list.value':  search_term.lower() } }
                    ],
                },})
    if (custom_fields and single_field):
        #create a bool must term which is the custom field identifier
        #cust_str = 'custom_fields.value.raw' % (single_field)
        must_list.append({
                              'bool': {
                                  'must': {'prefix': { 'custom_field_list.name.raw':  single_field } }
                              }
                            })
    body = {
      'query':{
          'bool':{
              'must': must_list
          }
      },
      'aggs': {
        'autocomplete': {
          'terms': { 'field': field_to_search, 'size':100, 'include': search_regex }
        }
      },
      'size': 0,
    }

    result = es.search(body=body)
    #return the results in the right format
    data = [res["key"] for res in result["aggregations"]["autocomplete"]["buckets"]]
    return data


def create_temporary_index(batches, request, index_name):
    es = elasticsearch.Elasticsearch()
    t = time.time()
    store_type = "memory"
    if len(batches) > 100:
        store_type = "niofs"
    create_body = {
        "settings": {
            "index.store.type": store_type
        },
         "mappings" : {
            "_default_" : {
               "_all" : {"enabled" : False},
               

               "dynamic_templates" : [ {
                 "string_fields" : {
                   "match" : "ctab|std_ctab|canonical_smiles|original_smiles",
                   "match_mapping_type" : "string",
                   "mapping" : {
                        "type" : "string", "store" : "no", "include_in_all" : False        
                   }
                 }
               } ,


                {
                 "string_fields" : {
                   "match" : "*",
                   "match_mapping_type" : "string",
                   "mapping" : {
                     "type" : "string","store" : "no", "index_options": "docs","index" : "analyzed", "omit_norms" : True,
                       "fields" : {
                         "raw" : {"type": "string","store" : "no", "index" : "not_analyzed", "ignore_above" : 256}
                       }
                   }
                 }
               } 
            ]
        }
        }
    }
    # if(index_name == get_main_index_name()):
    #     create_body['mappings']['_source'] = { 'enabled':False }
    #index_name = get_temp_index_name(request, multi_batch_id)
    
    es.indices.create(
            index_name,
            body=create_body,
            ignore=400)
    
    bulk_items = []
    for item in batches:
        bulk_items.append({
                            "index" :
                                {
                                    "_id": str(item["id"]), 
                                    "_index": index_name,
                                    "_type": "batches"
                                }
                            })
        bulk_items.append(item)
    #Data is not refreshed!
    es.bulk(body=bulk_items)

def get_project_index_name(project):
    index_name = "%s__project__%s" % (ES_PREFIX, str(project.id))
    print(index_name)
    return index_name

def reindex_compound(dataset, id):
    #reindex the specified compound in the specified index
    index_name = get_main_index_name()
    es = elasticsearch.Elasticsearch()
    update_body = {
      "doc" : dataset,
      "detect_noop": "true"
    }
    return es.index(id=id, doc_type="batches" ,index=index_name, body=update_body, refresh=True)