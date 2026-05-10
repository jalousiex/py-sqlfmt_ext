-- CTE测试
with tbl1 as(
select a                                                                                                                          , --
       b                                                                                                                          , /*-*/
       c                                                                                                                          , /*-长长长长长长长长长长注释*/
       t.*                                                                                                                        ,
       cast(cast((cast(substring(ComAges, 1, PATINDEX('%年%', ComAges) - 1) as int) * 12 /*-*/
                  + cast(substring(ComAges, PATINDEX('%年%', ComAges) + 1, PATINDEX('%月%', ComAges) - PATINDEX('%年%', ComAges) - 1) as int)) * 1.00 / 12 as decimal(16, 1)) as varchar(10)) as ComAges,
       x
  from DW.mdm.employee_d t
 where --
       1 = 1 --
   and 1 = 1
) -- 对齐13
-- 对齐14
select t.EmpName     ,
       t.EmpRecordNum /*岗位序号, 0为主岗, 主岗在职是次岗的前提*/,
       t.EffSeq       /*日期相同时的生效序号, 大的生效*/,
       t.JobCode     ,
       t.PositionName
  from (
       select *
         from DW.mdm.employee_post_relation_more
       ) t --多岗, 多岗为常态
 where t.EmpRecordNum = 0
-- 顶行首注释
;