/*-- 逗号对齐测试：comma_align=False 不填充空白对齐末尾逗号*/
select EmpCode, -- 员工编码,
       curdate() - interval 1 day HRD_NAME,
       curdate() - interval 1 day as empNAME,
       IFNULL(`t3`.`abc`,`t1`.`cde` --
              ) ff,
       min(StatYM) over(partition by CompanyCode, MaterialCode, KxMaterialCode, RequireType) as StatYM_min, -- 组合最早出现时间
       max(StatYM) over() as StatYM_max, -- 整体填报最新时间
       t2.LineManagerPositionName2 as lmpname,
       * -- 直线经理岗位名称
  from DIM.DIM_EMPLOYEE_D as t1
  left outer join DWD.HR_EMPLOYEE_POST_REL_F as t2
    on t1.EmpCode = t2.EmpCode;
