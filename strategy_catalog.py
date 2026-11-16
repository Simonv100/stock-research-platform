from __future__ import annotations

from typing import Any


FASHION_COMPANIES: list[dict[str, str]] = [
    {"Symbol": "VSXY", "Name": "Victoria's Secret", "Region": "US", "SearchTerm": "Victoria's Secret"},
    {"Symbol": "ANF", "Name": "Abercrombie & Fitch", "Region": "US", "SearchTerm": "Abercrombie"},
    {"Symbol": "AEO", "Name": "American Eagle Outfitters", "Region": "US", "SearchTerm": "American Eagle clothing"},
    {"Symbol": "URBN", "Name": "Urban Outfitters", "Region": "US", "SearchTerm": "Urban Outfitters"},
    {"Symbol": "GAP", "Name": "Gap", "Region": "US", "SearchTerm": "Gap clothing"},
    {"Symbol": "AKA", "Name": "a.k.a. Brands Holding", "Region": "US", "SearchTerm": "a.k.a. Brands"},
    {"Symbol": "BKE", "Name": "Buckle", "Region": "US", "SearchTerm": "Buckle clothing"},
    {"Symbol": "BOOT", "Name": "Boot Barn Holdings", "Region": "US", "SearchTerm": "Boot Barn"},
    {"Symbol": "BRIA", "Name": "BrilliA", "Region": "US", "SearchTerm": "BrilliA lingerie"},
    {"Symbol": "BURL", "Name": "Burlington Stores", "Region": "US", "SearchTerm": "Burlington stores"},
    {"Symbol": "CAL", "Name": "Caleres", "Region": "US", "SearchTerm": "Caleres shoes"},
    {"Symbol": "CATO", "Name": "Cato", "Region": "US", "SearchTerm": "Cato fashions"},
    {"Symbol": "CRI", "Name": "Carter's", "Region": "US", "SearchTerm": "Carter's clothing"},
    {"Symbol": "CTRN", "Name": "Citi Trends", "Region": "US", "SearchTerm": "Citi Trends"},
    {"Symbol": "CURV", "Name": "Torrid Holdings", "Region": "US", "SearchTerm": "Torrid clothing"},
    {"Symbol": "DBGI", "Name": "Digital Brands Group", "Region": "US", "SearchTerm": "Digital Brands Group"},
    {"Symbol": "DLTH", "Name": "Duluth Holdings", "Region": "US", "SearchTerm": "Duluth Trading"},
    {"Symbol": "DXLG", "Name": "Destination XL Group", "Region": "US", "SearchTerm": "Destination XL"},
    {"Symbol": "GCO", "Name": "Genesco", "Region": "US", "SearchTerm": "Genesco shoes"},
    {"Symbol": "JEM", "Name": "707 Cayman Holdings", "Region": "US", "SearchTerm": "707 Cayman Holdings"},
    {"Symbol": "JILL", "Name": "J.Jill", "Region": "US", "SearchTerm": "J.Jill clothing"},
    {"Symbol": "LE", "Name": "Lands' End", "Region": "US", "SearchTerm": "Lands' End clothing"},
    {"Symbol": "LVLU", "Name": "Lulus Fashion Lounge Holdings", "Region": "US", "SearchTerm": "Lulus clothing"},
    {"Symbol": "MYSZ", "Name": "My Size", "Region": "US", "SearchTerm": "MySize clothing"},
    {"Symbol": "REF", "Name": "Reformation", "Region": "US", "SearchTerm": "Reformation clothing"},
    {"Symbol": "RENT", "Name": "Rent the Runway", "Region": "US", "SearchTerm": "Rent the Runway"},
    {"Symbol": "ROST", "Name": "Ross Stores", "Region": "US", "SearchTerm": "Ross Dress for Less"},
    {"Symbol": "SFIX", "Name": "Stitch Fix", "Region": "US", "SearchTerm": "Stitch Fix"},
    {"Symbol": "SHOE", "Name": "Shoe Station Group", "Region": "US", "SearchTerm": "Shoe Station"},
    {"Symbol": "TJX", "Name": "TJX Companies", "Region": "US", "SearchTerm": "TJ Maxx"},
    {"Symbol": "TLYS", "Name": "Tilly's", "Region": "US", "SearchTerm": "Tillys clothing"},
    {"Symbol": "ZUMZ", "Name": "Zumiez", "Region": "US", "SearchTerm": "Zumiez"},
    {"Symbol": "BIRK", "Name": "Birkenstock Holding", "Region": "US", "SearchTerm": "Birkenstock"},
    {"Symbol": "CROX", "Name": "Crocs", "Region": "US", "SearchTerm": "Crocs shoes"},
    {"Symbol": "DBI", "Name": "Designer Brands", "Region": "US", "SearchTerm": "DSW shoes"},
    {"Symbol": "FMFC", "Name": "Kandal M Venture", "Region": "US", "SearchTerm": "Kandal M Venture"},
    {"Symbol": "FOSL", "Name": "Fossil Group", "Region": "US", "SearchTerm": "Fossil watches"},
    {"Symbol": "RCKY", "Name": "Rocky Brands", "Region": "US", "SearchTerm": "Rocky boots"},
    {"Symbol": "SHOO", "Name": "Steven Madden", "Region": "US", "SearchTerm": "Steve Madden shoes"},
    {"Symbol": "VRA", "Name": "Vera Bradley", "Region": "US", "SearchTerm": "Vera Bradley"},
    {"Symbol": "WEYS", "Name": "Weyco Group", "Region": "US", "SearchTerm": "Florsheim shoes"},
    {"Symbol": "WWW", "Name": "Wolverine World Wide", "Region": "US", "SearchTerm": "Wolverine boots"},
    {"Symbol": "TPR", "Name": "Tapestry", "Region": "US", "SearchTerm": "Coach handbags"},
    {"Symbol": "CPRI", "Name": "Capri Holdings", "Region": "US", "SearchTerm": "Michael Kors"},
    {"Symbol": "RL", "Name": "Ralph Lauren", "Region": "US", "SearchTerm": "Ralph Lauren"},
    {"Symbol": "PVH", "Name": "PVH", "Region": "US", "SearchTerm": "Calvin Klein"},
    {"Symbol": "LEVI", "Name": "Levi Strauss", "Region": "US", "SearchTerm": "Levi's jeans"},
    {"Symbol": "LULU", "Name": "Lululemon", "Region": "US", "SearchTerm": "Lululemon"},
    {"Symbol": "DECK", "Name": "Deckers Outdoor", "Region": "US", "SearchTerm": "Hoka shoes"},
    {"Symbol": "NKE", "Name": "Nike", "Region": "US", "SearchTerm": "Nike shoes"},
    {"Symbol": "VFC", "Name": "VF Corporation", "Region": "US", "SearchTerm": "The North Face"},
    {"Symbol": "SKX", "Name": "Skechers", "Region": "US", "SearchTerm": "Skechers"},
    {"Symbol": "ONON", "Name": "On Holding", "Region": "Europe", "SearchTerm": "On Running shoes"},
    {"Symbol": "MC.PA", "Name": "LVMH", "Region": "Europe", "SearchTerm": "Louis Vuitton"},
    {"Symbol": "RMS.PA", "Name": "Hermes", "Region": "Europe", "SearchTerm": "Hermes fashion"},
    {"Symbol": "KER.PA", "Name": "Kering", "Region": "Europe", "SearchTerm": "Gucci"},
    {"Symbol": "MONC.MI", "Name": "Moncler", "Region": "Europe", "SearchTerm": "Moncler"},
    {"Symbol": "BRBY.L", "Name": "Burberry", "Region": "Europe", "SearchTerm": "Burberry"},
    {"Symbol": "ADS.DE", "Name": "Adidas", "Region": "Europe", "SearchTerm": "Adidas shoes"},
    {"Symbol": "PUM.DE", "Name": "Puma", "Region": "Europe", "SearchTerm": "Puma shoes"},
    {"Symbol": "ITX.MC", "Name": "Inditex", "Region": "Europe", "SearchTerm": "Zara clothing"},
    {"Symbol": "HM-B.ST", "Name": "H&M", "Region": "Europe", "SearchTerm": "H&M clothing"},
    {"Symbol": "BOSS.DE", "Name": "Hugo Boss", "Region": "Europe", "SearchTerm": "Hugo Boss"},
    {"Symbol": "ZAL.DE", "Name": "Zalando", "Region": "Europe", "SearchTerm": "Zalando"},
    {"Symbol": "JD.L", "Name": "JD Sports Fashion", "Region": "Europe", "SearchTerm": "JD Sports"},
]


INFRASTRUCTURE_COMPANIES: list[dict[str, str]] = [
    {"Symbol": "AENA.MC", "Name": "Aena", "Region": "Europe", "Type": "Airports", "MarketStructure": "Operator of Spain's 46 public-use airports under the state airport framework.", "Source": "https://www.aena.es/en/corporate/about-aena.html"},
    {"Symbol": "ADP.PA", "Name": "Groupe ADP", "Region": "Europe", "Type": "Airports", "MarketStructure": "Sole operator of the three Paris-region international airports.", "Source": "https://www.groupeadp.fr/en/group/activities/airports/"},
    {"Symbol": "FRA.DE", "Name": "Fraport", "Region": "Europe", "Type": "Airports", "MarketStructure": "Sole owner and operator of Frankfurt Airport.", "Source": "https://www.fraport.com/en/investor-relations/fraport-at-a-glance.html"},
    {"Symbol": "FLU.VI", "Name": "Flughafen Wien", "Region": "Europe", "Type": "Airports", "MarketStructure": "Sole owner-operator of Vienna International Airport.", "Source": "https://www.viennaairport.com/en/company/investor_relations"},
    {"Symbol": "FHZN.SW", "Name": "Flughafen Zurich", "Region": "Europe", "Type": "Airports", "MarketStructure": "Sole operator of Zurich Airport under a cantonal concession.", "Source": "https://www.flughafen-zuerich.ch/en/company/investor-relations"},
    {"Symbol": "GET.PA", "Name": "Getlink", "Region": "Europe", "Type": "Fixed-link rail", "MarketStructure": "Exclusive concession owner and operator of the Channel Tunnel through 2086.", "Source": "https://www.getlinkgroup.com/en/group/our-model/concession/"},
    {"Symbol": "DG.PA", "Name": "Vinci", "Region": "Europe", "Type": "Toll roads", "MarketStructure": "Long-term French state concessions covering about 4,400 km of motorway.", "Source": "https://www.vinci-autoroutes.com/en/the-group/our-concessions"},
    {"Symbol": "FGR.PA", "Name": "Eiffage", "Region": "Europe", "Type": "Toll roads", "MarketStructure": "APRR and AREA hold long-term concessions for about 2,300 km of French motorway.", "Source": "https://www.aprr.fr/en/group/aprr-in-brief"},
    {"Symbol": "NG.L", "Name": "National Grid", "Region": "Europe", "Type": "Electricity and gas networks", "MarketStructure": "Regulated transmission and distribution networks in the UK and US.", "Source": "https://www.nationalgrid.com/about-us/our-role"},
    {"Symbol": "TRN.MI", "Name": "Terna", "Region": "Europe", "Type": "Electricity transmission", "MarketStructure": "Italy's sole electricity transmission-system operator.", "Source": "https://www.terna.it/en/investors/terna-at-a-glance"},
    {"Symbol": "RED.MC", "Name": "Redeia", "Region": "Europe", "Type": "Electricity transmission", "MarketStructure": "Spain's sole electricity transmission-system operator.", "Source": "https://www.redeia.com/en/investors/business-model"},
    {"Symbol": "ENG.MC", "Name": "Enagas", "Region": "Europe", "Type": "Gas transmission", "MarketStructure": "Spain's gas transmission-system operator and principal grid owner.", "Source": "https://www.enagas.es/en/about-enagas/who-we-are/"},
    {"Symbol": "SRG.MI", "Name": "Snam", "Region": "Europe", "Type": "Gas transmission", "MarketStructure": "Italy's regulated gas transmission-system operator.", "Source": "https://www.snam.it/en/investors/snam-at-a-glance/"},
    {"Symbol": "UU.L", "Name": "United Utilities", "Region": "Europe", "Type": "Regulated water", "MarketStructure": "Appointed water and wastewater network for North West England.", "Source": "https://www.unitedutilities.com/corporate/about-us/who-we-are/"},
    {"Symbol": "SVT.L", "Name": "Severn Trent", "Region": "Europe", "Type": "Regulated water", "MarketStructure": "Appointed water and sewerage provider for the English Midlands.", "Source": "https://www.severntrent.com/about-us/our-business/"},
    {"Symbol": "PNN.L", "Name": "Pennon Group", "Region": "Europe", "Type": "Regulated water", "MarketStructure": "Owns appointed regional water and wastewater utilities in England.", "Source": "https://www.pennon-group.co.uk/about-us"},
    {"Symbol": "AWK", "Name": "American Water Works", "Region": "US", "Type": "Regulated water", "MarketStructure": "Largest US investor-owned water utility with regulated service territories.", "Source": "https://amwater.com/corp/about-american-water/who-we-are"},
    {"Symbol": "WTRG", "Name": "Essential Utilities", "Region": "US", "Type": "Regulated water and gas", "MarketStructure": "Regulated water and gas distribution franchises across multiple states.", "Source": "https://www.essential.co/who-we-are/"},
    {"Symbol": "KMI", "Name": "Kinder Morgan", "Region": "US", "Type": "Gas pipelines", "MarketStructure": "Operator of North America's largest natural-gas pipeline network.", "Source": "https://www.kindermorgan.com/business/gas-pipelines/"},
    {"Symbol": "WMB", "Name": "Williams Companies", "Region": "US", "Type": "Gas pipelines", "MarketStructure": "Transco is the highest-volume US natural-gas pipeline system.", "Source": "https://www.williams.com/operations/transco/"},
    {"Symbol": "ENB", "Name": "Enbridge", "Region": "Canada", "Type": "Oil and gas pipelines", "MarketStructure": "Operates the world's largest crude-oil pipeline network and major regulated gas assets.", "Source": "https://www.enbridge.com/about-us/what-we-do"},
    {"Symbol": "EPD", "Name": "Enterprise Products Partners", "Region": "US", "Type": "Pipelines and terminals", "MarketStructure": "Integrated pipeline, storage and export system centered on the Mont Belvieu NGL hub.", "Source": "https://www.enterpriseproducts.com/about/overview"},
    {"Symbol": "CCI", "Name": "Crown Castle", "Region": "US", "Type": "Communications infrastructure", "MarketStructure": "One of the three dominant US macro-tower infrastructure owners.", "Source": "https://investor.crowncastle.com/overview/default.aspx"},
    {"Symbol": "AMT", "Name": "American Tower", "Region": "US", "Type": "Communications infrastructure", "MarketStructure": "Largest global independent wireless-tower operator.", "Source": "https://www.americantower.com/our-company/who-we-are/"},
    {"Symbol": "TRP.TO", "Name": "TC Energy", "Region": "Canada", "Type": "Natural-gas pipelines", "MarketStructure": "Owns regulated interstate and interprovincial gas-pipeline systems with major right-of-way barriers.", "Source": "https://www.tcenergy.com/operations/natural-gas/"},
    {"Symbol": "CNR.TO", "Name": "Canadian National Railway", "Region": "Canada", "Type": "Freight rail", "MarketStructure": "One of Canada's two dominant transcontinental freight-rail networks.", "Source": "https://www.cn.ca/en/about-cn/"},
    {"Symbol": "TCL.AX", "Name": "Transurban", "Region": "Developed Asia-Pacific", "Type": "Toll roads", "MarketStructure": "Operates 22 toll roads under long-term concessions in Australia and North America.", "Source": "https://www.transurban.com/about-us"},
    {"Symbol": "APA.AX", "Name": "APA Group", "Region": "Developed Asia-Pacific", "Type": "Energy transmission", "MarketStructure": "Owns a difficult-to-replicate Australian gas-pipeline grid and regulated electricity interconnectors.", "Source": "https://www.apa.com.au/operations-and-projects/gas"},
    {"Symbol": "CIG", "Name": "Cemig", "Region": "Latin America", "Type": "Electricity distribution and transmission", "MarketStructure": "Operates regulated electricity-distribution and transmission concessions centered on Minas Gerais.", "Source": "https://ri.cemig.com.br/en/"},
    {"Symbol": "SBS", "Name": "Sabesp", "Region": "Latin America", "Type": "Water and wastewater", "MarketStructure": "Provides monopoly water and sewerage networks through long-term municipal contracts across most of Sao Paulo state.", "Source": "https://ri.sabesp.com.br/en/"},
    {"Symbol": "ASR", "Name": "Grupo Aeroportuario del Sureste", "Region": "Latin America", "Type": "Airports", "MarketStructure": "Operates airports including Cancun under long-term government concessions.", "Source": "https://www.asur.com.mx/our-airports/"},
    {"Symbol": "PAC", "Name": "Grupo Aeroportuario del Pacifico", "Region": "Latin America", "Type": "Airports", "MarketStructure": "Operates major Mexican and Jamaican airports under geographically exclusive concessions.", "Source": "https://www.aeropuertosgap.com.mx/en/"},
    {"Symbol": "OMAB", "Name": "Grupo Aeroportuario del Centro Norte", "Region": "Latin America", "Type": "Airports", "MarketStructure": "Administers 13 airports in central and northern Mexico under federal concessions.", "Source": "https://ir.oma.aero/es/"},
    {"Symbol": "CAAP", "Name": "Corporacion America Airports", "Region": "Latin America", "Type": "Airports", "MarketStructure": "Operates long-duration airport concessions across Argentina, Brazil, Uruguay and other markets.", "Source": "https://www.caap.aero/"},
    {"Symbol": "TGS", "Name": "Transportadora de Gas del Sur", "Region": "Latin America", "Type": "Gas transmission", "MarketStructure": "Operates Argentina's regulated southern gas-transmission concession.", "Source": "https://www.tgs.com.ar/"},
    {"Symbol": "EDN", "Name": "Edenor", "Region": "Latin America", "Type": "Electricity distribution", "MarketStructure": "Holds the exclusive regulated electricity-distribution concession for northern Buenos Aires and surrounding districts.", "Source": "https://www.edenor.com/inversores"},
    {"Symbol": "MOTV3.SA", "Name": "Motiva Infraestrutura de Mobilidade", "Region": "Latin America", "Type": "Transport concessions", "MarketStructure": "Operates Brazilian toll-road, urban-rail and airport concessions.", "Source": "https://www.motiva.com.br/en/"},
    {"Symbol": "CSMG3.SA", "Name": "Copasa", "Region": "Latin America", "Type": "Water and wastewater", "MarketStructure": "Holds hundreds of municipal water and sewerage concessions in Minas Gerais.", "Source": "https://ri.copasa.com.br/a-companhia/perfil-corporativo/"},
    {"Symbol": "SAPR11.SA", "Name": "Sanepar", "Region": "Latin America", "Type": "Water and wastewater", "MarketStructure": "Operates regulated municipal water and sewerage systems throughout Parana state.", "Source": "https://ri.sanepar.com.br/"},
    {"Symbol": "TAEE11.SA", "Name": "TAESA", "Region": "Latin America", "Type": "Electricity transmission", "MarketStructure": "Owns availability-based Brazilian transmission concessions with regulated revenue.", "Source": "https://ri.taesa.com.br/en/"},
    {"Symbol": "ISAE4.SA", "Name": "ISA Energia Brasil", "Region": "Latin America", "Type": "Electricity transmission", "MarketStructure": "Operates regulated high-voltage transmission concessions across Brazil.", "Source": "https://ri.isaenergiabrasil.com.br/"},
    {"Symbol": "RAIL3.SA", "Name": "Rumo", "Region": "Latin America", "Type": "Freight rail", "MarketStructure": "Controls major Brazilian freight-rail concessions linking agricultural regions to export ports.", "Source": "https://ri.rumolog.com/"},
    {"Symbol": "PINFRA.MX", "Name": "Promotora y Operadora de Infraestructura", "Region": "Latin America", "Type": "Toll roads", "MarketStructure": "Owns concession titles covering Mexican toll highways plus bridge and toll-system contracts.", "Source": "https://www.pinfra.com.mx/"},
    {"Symbol": "AMX", "Name": "America Movil", "Region": "Latin America", "Type": "Telecommunications networks", "MarketStructure": "Operates incumbent-scale fixed and mobile networks in concentrated Latin American telecommunications markets.", "Source": "https://www.americamovil.com/English/about-us/footprint/default.aspx"},
    {"Symbol": "AGUAS-A.SN", "Name": "Aguas Andinas", "Region": "Latin America", "Type": "Water and wastewater", "MarketStructure": "Operates the regulated water and sewerage concession serving Santiago and surrounding municipalities.", "Source": "https://www.aguasandinas.cl/"},
    {"Symbol": "PGE.WA", "Name": "PGE Polska Grupa Energetyczna", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Owns regulated regional electricity-distribution networks alongside generation and supply businesses.", "Source": "https://www.gkpge.pl/pge-group/about-us/business-areas/distribution"},
    {"Symbol": "TPE.WA", "Name": "Tauron Polska Energia", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Controls a regulated distribution network serving southern Poland.", "Source": "https://www.tauron.pl/tauron/o-tauronie"},
    {"Symbol": "ENA.WA", "Name": "Enea", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Owns the regulated electricity-distribution network across north-western Poland.", "Source": "https://www.enea.pl/en"},
    {"Symbol": "TEL.RO", "Name": "Transelectrica", "Region": "Emerging Europe", "Type": "Electricity transmission", "MarketStructure": "Romania's regulated national electricity transmission-system operator.", "Source": "https://www.transelectrica.ro/en"},
    {"Symbol": "TGN.RO", "Name": "Transgaz", "Region": "Emerging Europe", "Type": "Gas transmission", "MarketStructure": "Romania's licensed national natural-gas transmission-system operator.", "Source": "https://www.transgaz.ro/en"},
    {"Symbol": "EL.RO", "Name": "Electrica", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Owns regulated regional electricity-distribution concessions covering much of Romania.", "Source": "https://www.electrica.ro/"},
    {"Symbol": "ADMIE.AT", "Name": "ADMIE Holding", "Region": "Emerging Europe", "Type": "Electricity transmission", "MarketStructure": "Listed holding company for the operator of Greece's monopoly high-voltage transmission grid.", "Source": "https://admieholding.gr/en/"},
    {"Symbol": "AIA.AT", "Name": "Athens International Airport", "Region": "Emerging Europe", "Type": "Airports", "MarketStructure": "Operates Athens' principal airport under an exclusive long-term concession.", "Source": "https://www.aia.gr/"},
    {"Symbol": "TAVHL.IS", "Name": "TAV Airports", "Region": "Emerging Europe", "Type": "Airports", "MarketStructure": "Operates airports in Turkey and other emerging markets under long-term concessions.", "Source": "https://tavairports.com/"},
    {"Symbol": "ENJSA.IS", "Name": "Enerjisa Enerji", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Operates three regulated regional electricity-distribution concessions in Turkey.", "Source": "https://www.enerjisa.com.tr/"},
    {"Symbol": "5110.SR", "Name": "Saudi Electricity Company", "Region": "Middle East and Africa", "Type": "Electricity networks", "MarketStructure": "State-backed operator of Saudi Arabia's national transmission and dominant regulated distribution system.", "Source": "https://www.se.com.sa/"},
    {"Symbol": "2082.SR", "Name": "ACWA Power", "Region": "Middle East and Africa", "Type": "Power and water concessions", "MarketStructure": "Develops and operates power-generation and desalination concessions backed by long-term offtake contracts.", "Source": "https://www.acwapower.com/en/what-we-do/"},
    {"Symbol": "QGTS.QA", "Name": "Nakilat", "Region": "Middle East and Africa", "Type": "LNG shipping infrastructure", "MarketStructure": "Owns one of the world's largest LNG-carrier fleets, primarily secured by long-duration charter contracts tied to Qatar's LNG exports.", "Source": "https://www.nakilat.com/our-fleet/"},
    {"Symbol": "7010.SR", "Name": "Saudi Telecom Company", "Region": "Middle East and Africa", "Type": "Telecommunications networks", "MarketStructure": "Saudi Arabia's incumbent fixed-line operator and largest member of a spectrum-constrained mobile oligopoly.", "Source": "https://www.stc.com.sa/"},
    {"Symbol": "TKG.JO", "Name": "Telkom SA", "Region": "Middle East and Africa", "Type": "Fixed and mobile telecommunications", "MarketStructure": "South Africa's incumbent fixed-line network owner, with extensive national fibre and wholesale infrastructure.", "Source": "https://group.telkom.co.za/"},
    {"Symbol": "VOD.JO", "Name": "Vodacom Group", "Region": "Middle East and Africa", "Type": "Telecommunications networks", "MarketStructure": "One of the two dominant South African mobile networks, with scarce spectrum and extensive tower and fibre infrastructure.", "Source": "https://www.vodacom.com/what-we-do.php"},
    {"Symbol": "MTN.JO", "Name": "MTN Group", "Region": "Middle East and Africa", "Type": "Telecommunications networks", "MarketStructure": "Operates large-scale spectrum-constrained mobile networks across concentrated African telecommunications markets.", "Source": "https://www.mtn.com/"},
    {"Symbol": "POWERGRID.NS", "Name": "Power Grid Corporation of India", "Region": "Emerging Asia", "Type": "Electricity transmission", "MarketStructure": "India's dominant interstate electricity-transmission utility and national grid operator.", "Source": "https://www.powergrid.in/en"},
    {"Symbol": "GAIL.NS", "Name": "GAIL India", "Region": "Emerging Asia", "Type": "Gas transmission", "MarketStructure": "Operates India's largest natural-gas pipeline network under regulated tariff and access arrangements.", "Source": "https://gailonline.com/"},
    {"Symbol": "CONCOR.NS", "Name": "Container Corporation of India", "Region": "Emerging Asia", "Type": "Rail freight terminals", "MarketStructure": "Operates a nationwide network of inland container depots and rail-linked logistics terminals.", "Source": "https://www.concorindia.co.in/"},
    {"Symbol": "INDUSTOWER.NS", "Name": "Indus Towers", "Region": "Emerging Asia", "Type": "Communications infrastructure", "MarketStructure": "One of India's largest independent tower networks, with high site-replication barriers.", "Source": "https://www.industowers.com/"},
    {"Symbol": "ADANIPORTS.NS", "Name": "Adani Ports and Special Economic Zone", "Region": "Emerging Asia", "Type": "Ports", "MarketStructure": "India's largest private port operator, controlling a nationwide portfolio of port concessions and terminals.", "Source": "https://www.adaniports.com/"},
    {"Symbol": "IGL.NS", "Name": "Indraprastha Gas", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Operates licensed city-gas distribution networks across Delhi and adjoining geographic areas.", "Source": "https://www.iglonline.net/"},
    {"Symbol": "MGL.NS", "Name": "Mahanagar Gas", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Holds city-gas distribution authorizations covering Mumbai and nearby districts.", "Source": "https://www.mahanagargas.com/"},
    {"Symbol": "ATGL.NS", "Name": "Adani Total Gas", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Builds and operates licensed gas-distribution networks within awarded Indian geographic areas.", "Source": "https://www.adanigas.com/"},
    {"Symbol": "0576.HK", "Name": "Zhejiang Expressway", "Region": "Emerging Asia", "Type": "Toll roads", "MarketStructure": "Operates major Zhejiang expressways under government toll concessions.", "Source": "https://www.zjec.com.cn/en/"},
    {"Symbol": "0694.HK", "Name": "Beijing Capital International Airport", "Region": "Emerging Asia", "Type": "Airports", "MarketStructure": "Operates Beijing Capital Airport under state-granted airport operating rights.", "Source": "https://www.bcia.com.cn/"},
    {"Symbol": "0144.HK", "Name": "China Merchants Port Holdings", "Region": "Emerging Asia", "Type": "Ports", "MarketStructure": "Owns strategic port terminals through long-term operating rights and concessions.", "Source": "https://www.cmport.com.hk/EN/"},
    {"Symbol": "AOT.BK", "Name": "Airports of Thailand", "Region": "Emerging Asia", "Type": "Airports", "MarketStructure": "State-controlled operator of Thailand's six principal airports, including Bangkok's two gateways.", "Source": "https://www.airportthai.co.th/en/homeen/"},
    {"Symbol": "BEM.BK", "Name": "Bangkok Expressway and Metro", "Region": "Emerging Asia", "Type": "Toll roads and urban rail", "MarketStructure": "Operates Bangkok expressways and metro lines under long-term public concessions.", "Source": "https://www.bemplc.co.th/"},
    {"Symbol": "5347.KL", "Name": "Tenaga Nasional", "Region": "Emerging Asia", "Type": "Electricity transmission and distribution", "MarketStructure": "Owns Peninsular Malaysia's principal regulated transmission and distribution networks.", "Source": "https://www.tnb.com.my/about-tnb/corporate-profile"},
    {"Symbol": "6033.KL", "Name": "PETRONAS Gas", "Region": "Emerging Asia", "Type": "Gas transmission", "MarketStructure": "Operates Malaysia's Peninsular Gas Utilisation network under regulated third-party-access arrangements.", "Source": "https://www.petronas.com/pgb/our-business"},
    {"Symbol": "5246.KL", "Name": "Westports Holdings", "Region": "Emerging Asia", "Type": "Ports", "MarketStructure": "Concession terminal operator handling approximately 80% of Port Klang's container traffic.", "Source": "https://www.westportsholdings.com/about-us/"},
    {"Symbol": "5209.KL", "Name": "Gas Malaysia", "Region": "Emerging Asia", "Type": "Gas distribution", "MarketStructure": "Licensed operator of Peninsular Malaysia's natural-gas distribution system.", "Source": "https://www.gasmalaysia.com/about-us-overview/"},
    {"Symbol": "2633.TW", "Name": "Taiwan High Speed Rail", "Region": "Emerging Asia", "Type": "High-speed rail", "MarketStructure": "Sole operator of Taiwan's high-speed railway under a build-operate-transfer concession.", "Source": "https://en.thsrc.com.tw/corp/"},
    {"Symbol": "HTWS.L", "Name": "Helios Towers", "Region": "Middle East and Africa", "Type": "Communications infrastructure", "MarketStructure": "Independent shared-tower operator across African markets and Oman; scarce tower sites and long-term mobile-operator contracts create infrastructure entry barriers.", "Source": "https://www.heliostowers.com/who-we-are/at-a-glance/"},
    {"Symbol": "AAF.L", "Name": "Airtel Africa", "Region": "Middle East and Africa", "Type": "Telecommunications networks", "MarketStructure": "Licensed mobile-network operator across 14 African markets, with spectrum-constrained voice and data networks alongside mobile-money services.", "Source": "https://www.airtel.africa/investment-case"},
    {"Symbol": "GND.JO", "Name": "Grindrod", "Region": "Middle East and Africa", "Type": "Ports and rail logistics", "MarketStructure": "Owns concession-based port and terminal interests including Maputo Port and linked rail infrastructure in southern Africa; also operates competitive logistics businesses.", "Source": "https://www.grindrod.com/solutions/port-and-terminals"},
    {"Symbol": "VEON", "Name": "VEON", "Region": "Emerging Asia", "Type": "Telecommunications networks", "MarketStructure": "Emerging-market mobile-network group including Beeline Kazakhstan, one of Kazakhstan's three mobile operators; not a pure Kazakhstan utility.", "Source": "https://www.veon.com/newsroom/press-releases/beeline-kazakhstan-signs-network-sharing-partnership-in-support-of-rural-broadband-initiative"},
    {"Symbol": "CEZ.PR", "Name": "CEZ", "Region": "Emerging Europe", "Type": "Electricity distribution", "MarketStructure": "Integrated utility owning the sole electricity distributor within its licensed Czech service areas; also owns generation and supply businesses.", "Source": "https://www.cezdistribuce.cz/en"},
    {"Symbol": "IGN1L.VS", "Name": "Ignitis Group", "Region": "Emerging Europe", "Type": "Electricity and gas distribution", "MarketStructure": "Baltic integrated utility owning regulated electricity and gas distribution networks through Energijos Skirstymo Operatorius.", "Source": "https://nasdaqbaltic.com/statistics/en/instrument/LT0000115768/company"},
    {"Symbol": "TSM1T.TL", "Name": "Tallinna Sadam", "Region": "Emerging Europe", "Type": "Ports", "MarketStructure": "State-controlled operator of Estonia's principal cargo and passenger port complex.", "Source": "https://www.ts.ee/en/company/"},
    {"Symbol": "TVE1T.TL", "Name": "Tallinna Vesi", "Region": "Emerging Europe", "Type": "Water and wastewater", "MarketStructure": "Owns Tallinn's integrated drinking-water, sewerage and wastewater-treatment assets under exclusive service arrangements.", "Source": "https://nasdaqbaltic.com/statistics/en/instrument/EE3100026436/company"},
    {"Symbol": "ALUP11.SA", "Name": "Alupar Investimento", "Region": "Latin America", "Type": "Electricity transmission", "MarketStructure": "Owns electricity transmission systems principally under long-term regulated concessions in Brazil and other Latin American markets.", "Source": "https://ri.alupar.com.br/a-companhia/perfil-corporativo/"},
    {"Symbol": "CPLE3.SA", "Name": "Copel", "Region": "Latin America", "Type": "Electricity transmission and distribution", "MarketStructure": "Integrated utility owning extensive regulated electricity transmission and distribution networks in Brazil.", "Source": "https://ri.copel.com/en/copel/corporate-profile/"},
    {"Symbol": "SITES1A-1.MX", "Name": "Operadora de Sites Mexicanos", "Region": "Latin America", "Type": "Communications infrastructure", "MarketStructure": "Mexico's largest owner and operator of passive telecommunications infrastructure by site count.", "Source": "https://www.telesites.com.mx/que-hacemos.html"},
    {"Symbol": "CLNX.MC", "Name": "Cellnex Telecom", "Region": "Europe", "Type": "Communications infrastructure", "MarketStructure": "Independent European tower operator with difficult-to-replicate sites and long-term customer agreements.", "Source": "https://www.cellnex.com/about-cellnex/"},
    {"Symbol": "INW.MI", "Name": "INWIT", "Region": "Europe", "Type": "Communications infrastructure", "MarketStructure": "Major Italian shared wireless-infrastructure operator whose model avoids duplicative tower networks.", "Source": "https://www.inwit.it/en/about-us/"},
    {"Symbol": "ELI.BR", "Name": "Elia Group", "Region": "Europe", "Type": "Electricity transmission", "MarketStructure": "Parent of regulated high-voltage transmission-system operators in Belgium and Germany.", "Source": "https://www.entsoe.eu/about/inside-entsoe/members/"},
    {"Symbol": "FLUX.BR", "Name": "Fluxys Belgium", "Region": "Europe", "Type": "Gas transmission and storage", "MarketStructure": "Operates Belgium's gas transmission pipelines, LNG terminal and underground storage under regulated arrangements.", "Source": "https://www.fluxys.com/en/about-us/fluxys-belgium"},
    {"Symbol": "RENE.LS", "Name": "REN", "Region": "Europe", "Type": "Electricity transmission", "MarketStructure": "Operator of Portugal's national electricity transmission infrastructure under regulated arrangements.", "Source": "https://www.entsoe.eu/about/inside-entsoe/members/"},
    {"Symbol": "IG.MI", "Name": "Italgas", "Region": "Europe", "Type": "Gas distribution", "MarketStructure": "Manages regulated gas-distribution networks through local concessions, alongside growing water-network operations.", "Source": "https://www.italgas.it/en/about-us/"},
    {"Symbol": "ENAV.MI", "Name": "ENAV", "Region": "Europe", "Type": "Air-navigation infrastructure", "MarketStructure": "Italy's national air-navigation provider operating airport control towers and area-control centres.", "Source": "https://www.enav.it/en"},
    {"Symbol": "VPK.AS", "Name": "Vopak", "Region": "Europe", "Type": "Storage and terminal infrastructure", "MarketStructure": "Operates strategic storage and terminal sites with difficult-to-replicate port access and long-duration customer relationships.", "Source": "https://www.vopak.com/discover-our-story"},
    {"Symbol": "HHFA.DE", "Name": "Hamburger Hafen und Logistik", "Region": "Europe", "Type": "Ports and intermodal terminals", "MarketStructure": "Operates scarce port-terminal and linked intermodal infrastructure centred on Hamburg.", "Source": "https://hhla.de/en/the-power-of-networks"},
    {"Symbol": "H.TO", "Name": "Hydro One", "Region": "Canada", "Type": "Electricity transmission and distribution", "MarketStructure": "Large-scale regulated electricity transmission and distribution utility in Ontario.", "Source": "https://www.hydroone.com/investor-relations"},
    {"Symbol": "EMA.TO", "Name": "Emera", "Region": "Canada", "Type": "Regulated electricity and gas utilities", "MarketStructure": "Owns regulated electric and gas utilities and pipeline infrastructure across Canada, the US and Caribbean.", "Source": "https://www.emera.com/companies"},
    {"Symbol": "PPL.TO", "Name": "Pembina Pipeline", "Region": "Canada", "Type": "Pipelines and terminals", "MarketStructure": "Owns difficult-to-replicate pipelines, gathering and processing facilities, storage and export infrastructure.", "Source": "https://www.pembina.com/about/"},
    {"Symbol": "ALA.TO", "Name": "AltaGas", "Region": "Canada", "Type": "Regulated utilities and midstream", "MarketStructure": "Diversified infrastructure company combining regulated gas utilities with contracted midstream assets.", "Source": "https://www.altagas.ca/about"},
    {"Symbol": "BIPC.TO", "Name": "Brookfield Infrastructure Corporation", "Region": "Canada", "Type": "Diversified infrastructure", "MarketStructure": "Corporate-form exposure to globally diversified regulated and contracted utility, transport, midstream and data infrastructure.", "Source": "https://bip.brookfield.com/"},
    {"Symbol": "UNP", "Name": "Union Pacific", "Region": "US", "Type": "Freight rail", "MarketStructure": "One of two dominant western-US Class I rail networks, with difficult-to-replicate rights-of-way and port connections.", "Source": "https://www.up.com/aboutup/corporate_info/uprrover/index.htm"},
    {"Symbol": "CSX", "Name": "CSX", "Region": "US", "Type": "Freight rail", "MarketStructure": "One of the dominant eastern-US Class I rail networks, with extensive port links and rights-of-way.", "Source": "https://www.csx.com/index.cfm/about-us/company-overview/"},
    {"Symbol": "SBAC", "Name": "SBA Communications", "Region": "US", "Type": "Communications infrastructure", "MarketStructure": "One of the leading independent owners of wireless towers and related infrastructure in concentrated tower markets.", "Source": "https://www.sbasite.com/"},
    {"Symbol": "0002.HK", "Name": "CLP Holdings", "Region": "Developed Asia-Pacific", "Type": "Electricity networks", "MarketStructure": "Regulated vertically integrated electricity system serving Kowloon and the New Territories, alongside diversified Asian generation assets.", "Source": "https://www.clpgroup.com/en/about-clp/our-business/hong-kong.html"},
    {"Symbol": "0003.HK", "Name": "Hong Kong and China Gas", "Region": "Developed Asia-Pacific", "Type": "Gas distribution", "MarketStructure": "Incumbent Hong Kong town-gas network plus extensive licensed mainland Chinese city-gas networks.", "Source": "https://www.towngas.com/en/About-Us/Company-Profile"},
    {"Symbol": "0006.HK", "Name": "Power Assets Holdings", "Region": "Developed Asia-Pacific", "Type": "Regulated utilities", "MarketStructure": "Diversified ownership of regulated electricity and gas networks across multiple markets.", "Source": "https://www.powerassets.com/en/about-us/business-profile"},
    {"Symbol": "0066.HK", "Name": "MTR Corporation", "Region": "Developed Asia-Pacific", "Type": "Urban rail", "MarketStructure": "Incumbent Hong Kong railway operator under government operating arrangements, with overseas rail concessions and property operations.", "Source": "https://www.mtr.com.hk/en/corporate/operations/profile_index.html"},
    {"Symbol": "0135.HK", "Name": "Kunlun Energy", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Operates licensed city-gas networks and an extensive pipeline system serving millions of customers across China.", "Source": "https://www.kunlun.com.hk/"},
    {"Symbol": "0270.HK", "Name": "Guangdong Investment", "Region": "Emerging Asia", "Type": "Water infrastructure", "MarketStructure": "Owns strategic water-supply infrastructure including the Dongjiang system supplying Hong Kong; also owns non-water businesses.", "Source": "https://www.gdi.com.hk/"},
    {"Symbol": "0371.HK", "Name": "Beijing Enterprises Water Group", "Region": "Emerging Asia", "Type": "Water and wastewater", "MarketStructure": "Large municipal water and wastewater concession and public-private-partnership operator across China.", "Source": "https://www.bewg.net/"},
    {"Symbol": "0384.HK", "Name": "China Gas Holdings", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Large trans-regional portfolio of licensed city-gas distribution networks in China.", "Source": "https://www.chinagasholdings.com.hk/"},
    {"Symbol": "0788.HK", "Name": "China Tower", "Region": "Emerging Asia", "Type": "Communications infrastructure", "MarketStructure": "Dominant nationwide shared telecom-tower infrastructure provider in China.", "Source": "https://www.china-tower.com/en/about/about.shtml"},
    {"Symbol": "1052.HK", "Name": "Yuexiu Transport Infrastructure", "Region": "Emerging Asia", "Type": "Toll roads", "MarketStructure": "Portfolio of Chinese expressways operated under long-duration toll concessions.", "Source": "https://www.yuexiutransport.com/"},
    {"Symbol": "1193.HK", "Name": "China Resources Gas", "Region": "Emerging Asia", "Type": "City-gas distribution", "MarketStructure": "Large portfolio of licensed municipal city-gas networks across China.", "Source": "https://crgas.com.hk/"},
    {"Symbol": "2638.HK", "Name": "HK Electric Investments", "Region": "Developed Asia-Pacific", "Type": "Electricity networks", "MarketStructure": "Scheme-of-Control-regulated electricity utility serving Hong Kong Island and Lamma Island; listed as share-stapled units.", "Source": "https://www.hkelectric.com/en/our-operations/electricity-information"},
    {"Symbol": "ADANIENSOL.NS", "Name": "Adani Energy Solutions", "Region": "Emerging Asia", "Type": "Electricity transmission and distribution", "MarketStructure": "Large private Indian transmission operator with regulated Mumbai electricity distribution.", "Source": "https://www.adanienergysolutions.com/about-us"},
    {"Symbol": "GPPL.NS", "Name": "Gujarat Pipavav Port", "Region": "Emerging Asia", "Type": "Ports", "MarketStructure": "Private concession port with strategic rail and maritime connectivity in Gujarat.", "Source": "https://www.gujaratpipavav.com/"},
    {"Symbol": "IRB.NS", "Name": "IRB Infrastructure Developers", "Region": "Emerging Asia", "Type": "Toll roads", "MarketStructure": "Developer and operator of Indian toll-road concessions; also has construction exposure.", "Source": "https://www.irb.co.in/"},
    {"Symbol": "TORNTPOWER.NS", "Name": "Torrent Power", "Region": "Emerging Asia", "Type": "Electricity distribution", "MarketStructure": "Operates licensed and franchised electricity distribution territories alongside generation businesses.", "Source": "https://www.torrentpower.com/"},
    {"Symbol": "015760.KS", "Name": "Korea Electric Power Corporation", "Region": "Developed Asia-Pacific", "Type": "Electricity networks", "MarketStructure": "State-controlled incumbent responsible for South Korean electricity transmission, distribution and marketing.", "Source": "https://home.kepco.co.kr/kepco/EN/A/htmlView/ENAAHP001.do?menuCd=EN010101"},
    {"Symbol": "036460.KS", "Name": "Korea Gas Corporation", "Region": "Developed Asia-Pacific", "Type": "Gas transmission and LNG", "MarketStructure": "State-backed South Korean national wholesale-gas and trunk-pipeline incumbent.", "Source": "https://www.kogas.or.kr/site/eng/1020101000000"},
    {"Symbol": "9020.T", "Name": "East Japan Railway", "Region": "Developed Asia-Pacific", "Type": "Rail network", "MarketStructure": "Incumbent eastern-Japan passenger railway with difficult-to-replicate rights-of-way and diversified station-property operations.", "Source": "https://www.jreast.co.jp/e/"},
    {"Symbol": "9021.T", "Name": "West Japan Railway", "Region": "Developed Asia-Pacific", "Type": "Rail network", "MarketStructure": "Incumbent western-Japan passenger and Shinkansen network with extensive railway rights-of-way.", "Source": "https://www.westjr.co.jp/global/en/about-us/"},
    {"Symbol": "9022.T", "Name": "Central Japan Railway", "Region": "Developed Asia-Pacific", "Type": "Rail network", "MarketStructure": "Controls the Tokaido Shinkansen corridor and associated conventional railway.", "Source": "https://global.jr-central.co.jp/en/company/about/outline.html"},
    {"Symbol": "AZJ.AX", "Name": "Aurizon Holdings", "Region": "Developed Asia-Pacific", "Type": "Rail infrastructure", "MarketStructure": "Manages extensive rail infrastructure including the regulated Central Queensland Coal Network; also has competitive haulage operations.", "Source": "https://www.aurizon.com.au/what-we-do/network"},
    {"Symbol": "ALX.AX", "Name": "Atlas Arteria", "Region": "Developed Asia-Pacific", "Type": "Toll roads", "MarketStructure": "Owns an international portfolio of long-duration toll-road concessions.", "Source": "https://www.atlasarteria.com/about-us/our-business/"},
    {"Symbol": "AIA.AX", "Name": "Auckland International Airport", "Region": "Developed Asia-Pacific", "Type": "Airports", "MarketStructure": "New Zealand's principal international gateway and regulated airport, represented by its Australian cross-listing.", "Source": "https://corporate.aucklandairport.co.nz/about"},
    {"Symbol": "2083.SR", "Name": "Marafiq", "Region": "Middle East and Africa", "Type": "Utility networks", "MarketStructure": "Integrated electricity, water, wastewater and cooling utility serving Saudi industrial cities.", "Source": "https://www.marafiq.com.sa/"},
]


STAR_PRINCIPLE_COMPANIES: list[dict[str, Any]] = []

STAR_PRINCIPLE_RESEARCH_REVIEWS: list[dict[str, Any]] = [
    {
        "Symbol": "ANET", "Name": "Arista Networks", "Region": "US",
        "Niche": "Global high-speed data-center Ethernet switching",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "Arista appears among suppliers in the accessed data-center switch report. "
            "This does not establish a current #1 share in a precisely defined "
            "high-speed or AI Ethernet sub-segment."
        ),
        "LeadershipSource": "https://www.marketsandmarkets.com/Market-Reports/data-center-switch-market-78270108.html",
        "GrowthEvidence": (
            "The broad switch report contains inconsistent forecast-horizon references "
            "and is not a verified >=10% growth source for the specifically assessed "
            "high-speed Ethernet niche. Its headline rate is not used for qualification."
        ),
        "GrowthSource": "https://www.marketsandmarkets.com/Market-Reports/data-center-switch-market-78270108.html",
        "GrowthRate": None, "GrowthPeriod": "Matching current forecast not established",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs dated vendor-share evidence and market growth for the same "
            "high-speed Ethernet niche. Broad-market vendor positioning and unclear "
            "report dates cannot establish either criterion."
        ),
    },
    {
        "Symbol": "CDNS", "Name": "Cadence Design Systems", "Region": "US",
        "Niche": "Global electronic design automation (EDA)",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "MarketsandMarkets identifies Cadence among major EDA vendors. The list "
            "is not a market-share ranking and does not prove unique #1 leadership."
        ),
        "LeadershipSource": "https://www.marketsandmarkets.com/Market-Reports/electronic-design-automation-market-55791440.html",
        "GrowthEvidence": (
            "The page, updated September 2024, quotes 9.8% forecast CAGR but also "
            "USD 14.5B in 2022 and USD 26.2B in 2028, which do not reconcile to that "
            "six-year rate. The forecast base needs clarification; no rate is accepted."
        ),
        "GrowthSource": "https://www.marketsandmarkets.com/Market-Reports/electronic-design-automation-market-55791440.html",
        "GrowthRate": None, "GrowthPeriod": "Forecast through 2028; base period unclear",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs an unambiguous current leadership source and a consistent market "
            "growth estimate for the same EDA niche. Neither vendor-list order nor "
            "rounding the quoted 9.8% up to 10% is acceptable."
        ),
    },
    {
        "Symbol": "SNPS", "Name": "Synopsys", "Region": "US",
        "Niche": "Global electronic design automation (EDA)",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "MarketsandMarkets identifies Synopsys among major EDA vendors but "
            "does not give a verified individual share or #1 rank in the accessed text."
        ),
        "LeadershipSource": "https://www.marketsandmarkets.com/Market-Reports/electronic-design-automation-market-55791440.html",
        "GrowthEvidence": (
            "The September 2024 page quotes 9.8% CAGR and inconsistent 2022/2028 "
            "market-size endpoints. This review does not accept that rate without "
            "clarification of its forecast base and scope."
        ),
        "GrowthSource": "https://www.marketsandmarkets.com/Market-Reports/electronic-design-automation-market-55791440.html",
        "GrowthRate": None, "GrowthPeriod": "Forecast through 2028; base period unclear",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs dated #1 leadership evidence and a consistent >=10% market growth "
            "estimate for the same niche. A semiconductor-IP sub-niche would need "
            "its own matching leadership and growth sources."
        ),
    },
    {
        "Symbol": "FTNT", "Name": "Fortinet", "Region": "US",
        "Niche": "Global next-generation firewalls (NGFW)",
        "ReviewStatus": "Near miss",
        "LeadershipEvidence": (
            "Fortinet is an established firewall supplier, but the accessed sources "
            "did not verify a unique #1 share in NGFW. Supplier-list order is not rank, "
            "and a broader appliance-unit share would not automatically match this niche."
        ),
        "LeadershipSource": "https://www.marketsandmarkets.com/Market-Reports/next-generation-firewall-ngfw-market-32240698.html",
        "GrowthEvidence": (
            "MarketsandMarkets' report title specifies 2023-2028 and its published "
            "description forecasts 11.4% CAGR for NGFW, reaching USD 8.6B in 2028. "
            "This is a forecast, not realized growth."
        ),
        "GrowthSource": "https://www.marketsandmarkets.com/Market-Reports/next-generation-firewall-ngfw-market-32240698.html",
        "GrowthRate": 0.114, "GrowthPeriod": "Forecast CAGR 2023-2028",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "The forecast exceeds 10%, but clear leadership in the same NGFW market "
            "was not verified. No #3 or other market rank is inferred from a vendor list."
        ),
    },
    {
        "Symbol": "ASM.AS", "Name": "ASM International", "Region": "Europe",
        "Niche": "Global single-wafer atomic layer deposition (ALD) equipment",
        "ReviewStatus": "Near miss",
        "LeadershipEvidence": (
            "Mordor describes ASM's Pulsar product line as maintaining single-wafer "
            "leadership. This is qualitative product-level evidence; a dated "
            "company market-share figure was not verified in the accessed sources."
        ),
        "LeadershipSource": "https://www.mordorintelligence.com/industry-reports/atomic-layer-deposition-market",
        "GrowthEvidence": (
            "The report forecasts 11.02% CAGR for cluster single-wafer ALD platforms "
            "in 2026-2031. The wider ALD market's 10.32% forecast is not substituted "
            "for this narrower segment."
        ),
        "GrowthSource": "https://www.mordorintelligence.com/industry-reports/atomic-layer-deposition-market",
        "GrowthRate": 0.1102, "GrowthPeriod": "Forecast CAGR 2026-2031",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Promising growth forecast, but the strict screen still needs unambiguous "
            "dated #1 company-level leadership evidence covering the same segment. "
            "An approximately 55% share figure was not verified and is not used."
        ),
    },
    {
        "Symbol": "FICO", "Name": "Fair Isaac", "Region": "US",
        "Niche": "US business-to-business credit-score licensing to lenders",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "A 2011 CFPB report describes FICO scores as the most widely used. This "
            "supports historical prominence, not a verified current market-share figure."
        ),
        "LeadershipSource": "https://www.consumerfinance.gov/data-research/research-reports/the-impact-of-differences-between-consumer-and-creditor-purchased-credit-scores/",
        "GrowthEvidence": (
            "No accessible independent growth estimate for this exact US score-licensing "
            "niche was established. FICO's own Scores revenue growth is not market growth."
        ),
        "GrowthSource": "", "GrowthRate": None, "GrowthPeriod": "Not established",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs current leadership evidence and a matching niche-market growth "
            "rate of at least 10%. The regulator's historical statement is explicitly "
            "dated 2011 and must not be treated as current proof."
        ),
    },
    {
        "Symbol": "VRSK", "Name": "Verisk Analytics", "Region": "US",
        "Niche": "US property-and-casualty insurance statistical and actuarial data services",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "Verisk describes its strategic data and technology role in insurance, "
            "but this review did not verify a #1 share in the specifically defined niche."
        ),
        "LeadershipSource": "https://www.verisk.com/company/newsroom/",
        "GrowthEvidence": (
            "A 2021 MarketsandMarkets report forecast 15.1% growth for broader insurance "
            "analytics through 2026. That broader software market is not a valid growth "
            "proxy for ISO-style P&C statistical and actuarial data services."
        ),
        "GrowthSource": "https://www.marketsandmarkets.com/Market-Reports/insurance-analytics-market-58298536.html",
        "GrowthRate": None, "GrowthPeriod": "Exact-niche growth not established",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs current leadership and growth evidence for the same P&C data-services "
            "niche. Vendor-list order is not a market ranking, and the broader 2021 "
            "analytics forecast is both scope-mismatched and dated."
        ),
    },
    {
        "Symbol": "BESI.AS", "Name": "BE Semiconductor Industries", "Region": "Europe",
        "Niche": "Global die-attach equipment",
        "ReviewStatus": "Near miss",
        "LeadershipEvidence": (
            "Mordor identifies Besi among the leading die-attach equipment incumbents, "
            "but does not establish its individual revenue share or a unique #1 rank."
        ),
        "LeadershipSource": "https://www.mordorintelligence.com/industry-reports/die-attach-equipment-market",
        "GrowthEvidence": (
            "The report forecasts the die-attach equipment market from USD 2.13B in "
            "2026 to USD 3.49B in 2031, a 10.36% CAGR. This is a forecast, not realized growth."
        ),
        "GrowthSource": "https://www.mordorintelligence.com/industry-reports/die-attach-equipment-market",
        "GrowthRate": 0.1036, "GrowthPeriod": "Forecast CAGR 2026-2031",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "The growth forecast clears 10%, but this review did not establish sole "
            "market leadership in that same die-attach niche. Hybrid-bonding leadership "
            "claims cannot automatically establish leadership of the broader market."
        ),
    },
    {
        "Symbol": "DSY.PA", "Name": "Dassault Systemes", "Region": "Europe",
        "Niche": "Global product lifecycle management (PLM) software",
        "ReviewStatus": "Does not meet",
        "LeadershipEvidence": (
            "Mordor estimates Siemens, Dassault Systemes and PTC jointly held 40-45% "
            "of PLM revenue in 2025; this does not establish Dassault's individual #1 rank."
        ),
        "LeadershipSource": "https://www.mordorintelligence.com/industry-reports/product-lifecycle-management-software-market",
        "GrowthEvidence": (
            "The report forecasts overall PLM software growth of 8.06% CAGR, from "
            "USD 50.17B in 2026 to USD 73.91B in 2031, below the 10% threshold."
        ),
        "GrowthSource": "https://www.mordorintelligence.com/industry-reports/product-lifecycle-management-software-market",
        "GrowthRate": 0.0806, "GrowthPeriod": "Forecast CAGR 2026-2031",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "The assessed overall PLM niche is below the growth threshold, and individual "
            "leadership was not established. This does not rule out a narrower niche; "
            "the faster-growing cloud segment needs its own matching leadership evidence."
        ),
    },
    {
        "Symbol": "HLMA.L", "Name": "Halma", "Region": "Europe",
        "Niche": "Safety, environmental and healthcare subsidiaries; no single assessed niche",
        "ReviewStatus": "Insufficient evidence",
        "LeadershipEvidence": (
            "Halma describes a decentralized portfolio of businesses operating in "
            "global niches. This establishes its operating model, not a quantified "
            "#1 position for a specifically assessed subsidiary or product market."
        ),
        "LeadershipSource": "https://www.halma.com/who-we-are",
        "GrowthEvidence": (
            "No matching niche-market growth rate was established in this review. "
            "Group organic revenue growth is not a substitute for niche-market growth."
        ),
        "GrowthSource": "https://www.halma.com/who-we-are/our-markets-and-their-long-term-growth-drivers",
        "GrowthRate": None, "GrowthPeriod": "Not established",
        "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": (
            "Needs a specific, economically relevant subsidiary/product niche with "
            "documented leadership and matching market growth. Being diversified "
            "does not itself disqualify the stock."
        ),
    },
]


def star_principle_catalog() -> list[dict[str, Any]]:
    rows = []
    for company in STAR_PRINCIPLE_COMPANIES:
        rows.append({
            **company, "ReviewStatus": "Evidence-qualified",
            "MissingEvidence": "", "GrowthEvidence": company.get("GrowthEvidence", ""),
        })
    for company in STAR_PRINCIPLE_NEAR_MISSES:
        rows.append({
            "Symbol": company["Symbol"], "Name": company["Name"],
            "Region": company["Region"], "Niche": company["Niche"],
            "ReviewStatus": "Near miss",
            "LeadershipEvidence": company["VerifiedEvidence"],
            "LeadershipSource": company["VerifiedSource"],
            "GrowthEvidence": "", "GrowthSource": "", "GrowthRate": None,
            "GrowthPeriod": "", "EvidenceAsOf": "Not recorded",
            "MissingEvidence": company["MissingEvidence"],
        })
    return rows + [dict(row) for row in STAR_PRINCIPLE_RESEARCH_REVIEWS]


def build_star_research_universe(
    holdings: list[dict[str, Any]], reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reviewed = {row["Symbol"]: row for row in reviews}
    universe = {}
    for holding in holdings:
        symbol = holding["Symbol"]
        universe[symbol] = dict(reviewed.get(symbol, {
            "Symbol": symbol, "Name": holding["Name"], "Region": holding["Region"],
            "Niche": "", "ReviewStatus": "Unreviewed",
            "LeadershipEvidence": "", "LeadershipSource": "",
            "GrowthEvidence": "", "GrowthSource": "", "GrowthRate": None,
            "GrowthPeriod": "", "EvidenceAsOf": "",
            "MissingEvidence": "Not yet researched. This is not a failed Star Principle assessment.",
        }))
    return [universe[symbol] for symbol in sorted(universe)]


STAR_PRINCIPLE_NEAR_MISSES: list[dict[str, str]] = [
    {
        "Symbol": "ASML.AS",
        "Name": "ASML Holding",
        "Region": "Europe",
        "Niche": "EUV photolithography systems",
        "VerifiedEvidence": (
            "ASML is the only company producing and selling EUV systems for chip production."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Extreme_ultraviolet_lithography",
        "MissingEvidence": (
            "No exact, freely accessible source was found stating at least 10% annual "
            "growth for the EUV lithography systems market itself."
        ),
    },
    {
        "Symbol": "AMZN",
        "Name": "Amazon",
        "Region": "US",
        "Niche": "Public cloud infrastructure through AWS",
        "VerifiedEvidence": (
            "AWS is widely documented as the largest public-cloud infrastructure provider."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Amazon_Web_Services",
        "MissingEvidence": (
            "The accessible leadership source does not provide the required current "
            "quantified share, and no exact public source was verified for >=10% "
            "growth in the same IaaS/PaaS niche."
        ),
    },
    {
        "Symbol": "NVDA",
        "Name": "NVIDIA",
        "Region": "US",
        "Niche": "AI data-centre GPU accelerators",
        "VerifiedEvidence": (
            "NVIDIA's dominant role in data-centre GPU computing is well documented."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Nvidia",
        "MissingEvidence": (
            "No freely accessible independent source was verified that quantifies "
            "both current leadership and >=10% growth for the exact AI-accelerator niche."
        ),
    },
    {
        "Symbol": "CRWD",
        "Name": "CrowdStrike",
        "Region": "US",
        "Niche": "Cloud-native endpoint protection",
        "VerifiedEvidence": (
            "CrowdStrike is a prominent cloud-delivered endpoint-security platform."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/CrowdStrike",
        "MissingEvidence": (
            "No accessible source was verified proving clear #1 market share, and "
            "the exact endpoint-market growth source could not be publicly verified."
        ),
    },
    {
        "Symbol": "ISRG",
        "Name": "Intuitive Surgical",
        "Region": "US",
        "Niche": "Robotic-assisted soft-tissue surgery",
        "VerifiedEvidence": (
            "The da Vinci platform has the largest established robotic-surgery installed base."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Da_Vinci_Surgical_System",
        "MissingEvidence": (
            "The accessible source does not quantify a current market share, and no "
            "exact public >=10% market-growth source was verified for this narrow niche."
        ),
    },
    {
        "Symbol": "VEEV",
        "Name": "Veeva Systems",
        "Region": "US",
        "Niche": "Life-sciences cloud software",
        "VerifiedEvidence": (
            "Veeva serves the largest pharmaceutical companies with industry-specific cloud products."
        ),
        "VerifiedSource": "https://ir.veeva.com/",
        "MissingEvidence": (
            "Customer penetration is not quantified #1 market-share evidence, and "
            "same-niche market CAGR evidence was available only through paywalled reports."
        ),
    },
    {
        "Symbol": "SHOP",
        "Name": "Shopify",
        "Region": "US",
        "Niche": "Merchant-operated e-commerce store platforms",
        "VerifiedEvidence": (
            "Shopify operates one of the largest merchant storefront and commerce platforms."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Shopify",
        "MissingEvidence": (
            "Merchant count and GMV do not establish strict #1 share in a consistently "
            "defined niche, and no exact public >=10% niche-growth source was verified."
        ),
    },
    {
        "Symbol": "MELI",
        "Name": "MercadoLibre",
        "Region": "US",
        "Niche": "Latin American e-commerce marketplaces",
        "VerifiedEvidence": (
            "MercadoLibre is broadly documented as the leading regional e-commerce ecosystem."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/Mercado_Libre",
        "MissingEvidence": (
            "No accessible source was verified with a precise regional market-share "
            "figure and >=10% growth for the identically defined marketplace niche."
        ),
    },
    {
        "Symbol": "MSCI",
        "Name": "MSCI",
        "Region": "US",
        "Niche": "Non-US and emerging-market equity benchmarks",
        "VerifiedEvidence": (
            "MSCI indexes are extensively used as benchmarks for global investment products."
        ),
        "VerifiedSource": "https://en.wikipedia.org/wiki/MSCI",
        "MissingEvidence": (
            "Assets benchmarked to MSCI do not prove #1 market share, and the exact "
            "benchmark-licensing niche has no verified public >=10% growth source."
        ),
    },
]
