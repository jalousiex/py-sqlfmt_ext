select * from ODS_CLD.CLD_EDC_CRF_DATA_043 d
lateral view explode(cast(d.payload['itemGroups'] as ARRAY<VARIANT>)) ig_exp as ig