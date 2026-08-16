create view DWD.HR_EMPLOYEE_INFO_D as --
-- 替代 dwdim.dim_employee_d （改用ODS）
with W_EMPLOYEE_BASE as (
select EMPLID                                                     as EmpCode,
       ROW_NUMBER() --
             over(partition by EMPLID order by BGN_DTTM desc, /*-*/
                                               (ifnull(a,0)) asc)    rn       ,
  from ODS.PS_HPS_PERS2MDM_VW_001 t1 -- ods.PS_HPS_PERS2MDM_VW_001
 where 1 = 1 --t1.Rowkey=1
--and t1.Rowkey=1
       --and t1.Rowkey=1
) --
, -- 对齐1
W_CTE                as ( --
-- 对齐2
select *
  from W_EMPLOYEE_BASE t1 -- DW.mdm.employee_base
 where t1.RowKey = 1
) -- 对齐3
-- 对齐4
select *
  from W_CTE