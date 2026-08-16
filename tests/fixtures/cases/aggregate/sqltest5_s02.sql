select TJNY                                                                                   as '统计年月',
       DJBH                                                                                   as '单据编号',
       replace(replace(replace(replace(LXYSMC, CHAR(13),''),CHAR(10),''),CHAR(9),''),' ', '') as '客户名称导入',
       DJBH                                                                                   as '单据编号'
  from tab1;