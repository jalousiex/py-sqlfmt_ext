alter table t add column a int, add column b varchar(10), add column c date; alter table t modify column a bigint, drop column b, add index idx_a (a);
