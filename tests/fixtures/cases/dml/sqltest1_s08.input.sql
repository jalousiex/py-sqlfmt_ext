select c.OWNER       as schema_name                 ,
       c.TABLE_NAME  as table_name                 ,
       c.COLUMN_NAME as column_name                 ,
       c.COLUMN_ID   as ordinal_position,
       c.DATA_TYPE   as data_type       ,
       0             as is_identity
  from ALL_TAB_COLUMNS c