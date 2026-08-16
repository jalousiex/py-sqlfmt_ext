-- 物化视图
create materialized view DM.OA_AS_OPERATION_LOG_UO_F --
refresh auto
on
commit
partition by(OpDate) as
select *
  from lineitem;