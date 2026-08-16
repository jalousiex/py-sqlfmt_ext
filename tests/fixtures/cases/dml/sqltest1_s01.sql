/*-- DML测试*/
insert into mdm.employee_d_tmp (
       a,
       b,
       c
)
select EmpCode                                                                                            , -- 员工编码,
       curdate() - interval 1 day                                                               HRD_NAME  ,
       curdate() - interval 1 day                                                            as empNAME   ,
       IFNULL(`t3`.`abc`,`t1`.`cde` --
              )                                                                                 ff        ,
       min(StatYM) over(partition by CompanyCode, MaterialCode, KxMaterialCode, RequireType) as StatYM_min, -- 组合最早出现时间
       max(StatYM) over()                                                                    as StatYM_max, -- 整体填报最新时间
       t2.LineManagerPositionName2                                                           as lmpname   ,
       *                                                                                                    -- 直线经理岗位名称
  from DIM.DIM_EMPLOYEE_D as t1 -- mdmvw.vw_employee_base 取自mdm.employee_base 限制RowKey = 1
-- 可改使用DIM.DIM_EMPLOYEE_D 限制RowKey = 1
  left outer join DWD.HR_EMPLOYEE_POST_REL_F as t2 -- mdmvw.vw_employee_post_relation 取自mdm.employee_post_relation 限制RowKey = 1
-- 可改使用DWD.HR_EMPLOYEE_POST_REL_F 限制Rowkey=1，EmpRecordNum=0
    on t1.EmpCode = t2.EmpCode;