create view DWD.HR_EMPLOYEE_LEAVE_HIS_F as
select -- test
       case when HPS_TER_REASON in ('100', '105', '110', '115', '125', '130', '135') then '10'
       end as abc,
       t.*
  from DW.mdm.employee_d t --PS