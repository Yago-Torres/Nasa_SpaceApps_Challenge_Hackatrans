"""Explicit heuristics, NOT agronomic outcome predictions."""
ROTATIONS=[
 {'id':'current','name':'Current: cereal / cereal', 'years':[['winter wheat'],['barley']],
  'crop_diversity_count':2,'includes_legume':False,'includes_cover_crop':False},
 {'id':'legume','name':'Alternative A: cereal / grain legume', 'years':[['winter wheat'],['chickpea']],
  'crop_diversity_count':2,'includes_legume':True,'includes_cover_crop':False},
 {'id':'cover','name':'Alternative B: cereal / legume + cover', 'years':[['winter wheat'],['chickpea','winter cover crop']],
  'crop_diversity_count':3,'includes_legume':True,'includes_cover_crop':True},
]

def rotation_examples():
    return [{'kind':'modelled_scenario',**r,
             'interpretation':('Potential extra soil cover and/or crop diversity; requires crop-calendar, '
                 'water-demand, farmer constraint and soil review before field use.'),
             'verified_impact':None,
             'warning':'Illustrative sequences only. No yield, water saving or soil-carbon benefit is calculated.'}
            for r in ROTATIONS]
