select EmpCode                               ,
       max(Empname)       as Empname         ,
       group_concat(-- 拼接培训详细信息
                    concat('培训时间:', IFNULL(date_format(BeginDate,'yyyy-MM-dd'), 'NULL'), --
                           ',培训类型:', IFNULL(TrainTypeName, 'NULL'), --
                           ',储备级别:', IFNULL(ReserveLevelDescr, 'NULL'), --
                           ',项目名称:', IFNULL(TrainItemName, 'NULL'), --
                           ',培训评价:', IFNULL(cast(TrainEvaluResult as CHAR), 'NULL') --
                           ), '
' order by BeginDate asc) as trainning_detail
  from DWD.HR_EMPLOYEE_TRAINNING_F
 group by EmpCode;