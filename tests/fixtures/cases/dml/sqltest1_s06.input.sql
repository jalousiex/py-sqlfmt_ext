select d.study_oid                                                     ,
       JSON_EXTRACT_STRING(d.payload, '$.LocationOID') as site_id      ,
       JSON_EXTRACT_STRING(sub, '$.SubjectKey')        as subject_key  ,
       JSON_EXTRACT_STRING(d.payload, '$.StudyEventOID')
                                                       as folder_oid   ,
       JSON_EXTRACT_STRING(d.payload, '$.StudyEventRepeatKey')
                                                       as folder_key   ,
       d.form_oid                                                      ,
       JSON_EXTRACT_STRING(d.payload, '$.FormRepeatKey')
                                                       as form_key     ,
       JSON_EXTRACT_STRING(ig_obj, '$.ItemGroupOID')   as itemgroup_oid,
       ig_key                                          as item_oid     ,
       JSON_UNQUOTE(ig_val)                            as item_value   ,
       case when ig_val is null then 1
            else                     0
       end                                             as is_null      ,
       d.snapshot_dt                                                   ,
       d.DW_CREATED_DATE                                               ,
       d.DW_UPDATED_DATE
  from ODS_CLD.CLD_EDC_CRF_DATA_043 d
lateral view EXPLODE_JSON_ARRAY_JSON(JSON_EXTRACT(cast(d.payload as string), '$.subjects')) s as sub
lateral view EXPLODE_JSON_ARRAY_JSON(JSON_EXTRACT(sub, '$.data')) ig as ig_obj
lateral view explode_json_object(ig_obj) ig_kv as ig_key,
             ig_val
 where ig_key != 'ItemGroupOID';