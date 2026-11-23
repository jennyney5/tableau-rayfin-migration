These are some of challenges we noted while migrating reports to Power BI(regular reports).
Calculation semantics: Tableau LOD expressions, table calculations, and DAX filter context behave differently.
Visual dependencies: calculations may depend on visual grain, sorting, partitioning, or addressing.
Parameters and interactions: Tableau parameters and dashboard actions may require slicers, disconnected tables, field parameters, or native Power BI interactions.
Data types: floating-point values, dates, nulls, aggregation defaults, and formatting can change results.
Ambiguous source logic: captions, formulas, and business intent may conflict.
Relationships: cardinality and filter direction cannot safely be inferred from similar field names alone.
Security: Tableau user/group logic requires explicit Power BI RLS and identity mappings.