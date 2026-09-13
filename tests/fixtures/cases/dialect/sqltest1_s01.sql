create table dw.t (
       id       int64           ,
       name     varchar(20)     ,
       v1       string          ,
       v2       datev2          ,
       v3       datetimev2(3)   ,
       v4       decimalv3(10, 2),
       v5       largeint        ,
       v6       bitmap          ,
       v7 jsonb
);
