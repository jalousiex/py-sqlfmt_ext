-- alter table 单字段与多字段
alter table DIM.DIM_EMPLOYEE_D drop column DomainAccountCKD;

alter table DIM.DIM_EMPLOYEE_D add column DASource varchar(10)
comment '数据来源:BPM/PS' after Email;

alter table DIM.DIM_EMPLOYEE_D add column (
       a        int                                               ,
       DASource varchar(10)  comment '数据来源:BPM/PS' after Email,
       c        int
);