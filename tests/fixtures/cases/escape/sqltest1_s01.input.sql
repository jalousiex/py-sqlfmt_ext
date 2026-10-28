select EmpCode                                                  ,
       DomainAccount                        as domain_account    ,
       concat(Empname, '\\', DomainAccount) as display_name      ,
       case when SourceFlag = 'PS'        then 'internal'
            when DomainAccount like 'ex%' then 'external'
            else                               'internal'
       end                                  as user_type         ,
       Email                                as mail              ,
       DeptCode                             as dept_id_list          -- select *
  from DIM.DIM_EMPLOYEE_D e
 where e.delflag = 'N' and DeptName = '数据与AI服务部'
   and e.rowkey_DA = 1
   and e.HrStatus = 'A';
