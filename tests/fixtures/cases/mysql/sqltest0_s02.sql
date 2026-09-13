create table t (
       a          int                        ,
       b          double                     ,
       c          enum('x', 'y')             ,
       d          set('p')                   ,
       e          json                       ,
       f          time                       ,
       g          year                       ,
       h          varchar(10)                ,
       created_at time           default null
);
