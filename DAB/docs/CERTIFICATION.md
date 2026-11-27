# Codes, standards and certification path

What these blocks would have to meet in the United States, what that means for
the design, and how solid-state transformers are being certified today.

**How to read this.** I could search the web but could not open the primary
documents (the regulation and standards sites were not reachable from the
design environment, and UL standards are paywalled). Each claim is marked:

* **[S]** found in a search result quoting the regulation, a standards body or
  a test laboratory;
* **[2]** found only in a secondary source (manufacturer, consultant, forum);
* **[M]** from my own knowledge, not checked in this study.

None of this is legal or compliance advice. A test laboratory and the
authority having jurisdiction decide; section 8 says what to ask them.

## 1. Summary

1. **There is no dedicated product standard for a solid-state transformer.**
   Every source found agrees that products are certified against a
   combination of existing power-converter standards. [S][2]
2. **It will not be certified as a transformer.** Transformer standards cover
   wound components. The block is power conversion equipment and will be
   evaluated as such; the transformer standards apply only to the magnetic
   parts inside it. [M]
3. **The federal efficiency rule probably does not apply, but its numbers are
   the benchmark a customer will hold you to.** 99.06 % is the 2029 level for
   a 150 kVA three-phase low-voltage dry-type transformer, not for 10 kVA. The
   current design clears every low-voltage dry-type level up to 225 kVA.
4. **The non-isolated block is electrically an autotransformer**, and the
   electrical code's autotransformer rules shape how it can be installed.
5. **The largest design consequence is functional safety**: the over-voltage
   crowbar, short-circuit shutdown and neutral-loss shutdown will be examined
   as safety functions, which is easiest to pass if they are hardware, simple
   and duplicated. The revision E design already goes that way.

## 2. Federal efficiency rule (DOE, 10 CFR 431 Subpart K)

**What the rule covers.**

* Dry-type distribution transformers from 15 kVA up. [S] A single 10 kVA block
  is below that floor. A three-phase bank of three is 30 kVA and would be
  inside the range if it counted as a transformer at all.
* **Autotransformers are excluded** from the definition of a distribution
  transformer. [S] The non-isolated block is the electronic equivalent of one.
* The definition is built around a device that transfers power by
  electromagnetic induction between coils. [M] Whether an electronic converter
  is a "transformer" under the statute is a legal question I could not
  resolve; no source found addresses it.
* Efficiency for low-voltage dry-type units is determined at 35 % of nameplate
  load. [2] Ratings between table rows are interpolated. [S]

**The 2029 levels** (compliance for units manufactured from April 23, 2029 [S];
table values from a manufacturer's summary [2], to be checked against the
regulation):

| Three-phase kVA | 2029 efficiency | | Single-phase kVA | 2029 efficiency |
|---|---|---|---|---|
| 15 | 98.31 % | | 15 | 98.39 % |
| 30 | 98.58 % | | 25 | 98.60 % |
| 45 | 98.72 % | | 37.5 | 98.74 % |
| 75 | 98.88 % | | 50 | 98.81 % |
| 112.5 | 98.99 % | | 75 | 98.95 % |
| **150** | **99.06 %** | | 100 | 99.02 % |
| 225 | 99.15 % | | 167 | 99.09 % |
| 300 | 99.22 % | | 250 | 99.16 % |

**What that means here.**

* 99.06 % is the level for a 150 kVA three-phase unit, which is five blocks
  per phase. A 30 kVA bank would be held to 98.58 %, and a single-phase
  15 kVA unit to 98.39 %.
* A bank's efficiency is the efficiency of its blocks. The revision E
  non-isolated block is predicted at 99.21 % at 35 % load, so it meets every
  level up to 225 kVA and is on the line at 300 kVA.
* If only the 30 kVA level (98.58 %) had to be met, the earlier cost-optimised
  chopper would still fall short (about 98.4 % under the stricter loss model),
  but a much lighter redesign than revision E would do.
* **The rule may change.** In June 2026 DOE opened a request for information
  on how the 2029 standards interact with supply-chain and national-security
  concerns. No delay had been proposed in what I found. [S][2]

**Other efficiency regimes.** Canada regulates dry-type transformers
separately [S]; state rules and utility or customer specifications often
adopt the DOE table regardless of legal scope. [M]

## 3. Product safety listing

To be installed under the electrical code the block needs a listing mark from
a nationally recognised testing laboratory. [M] The candidates:

| Standard | What it covers | Fit |
|---|---|---|
| **UL 1741** | Inverters, converters, controllers and interconnection equipment for distributed energy resources. Its scope includes stand-alone as well as utility-interactive equipment, and converters are held to the inverter requirements. [S] Sources describe it as the usual US route for solid-state transformers in storage and renewables. [2] | Best fit if any source sits behind the block (storage, solar, generator), which the bidirectional requirement implies. Grid-support and interconnection testing (the SA/SB supplements, IEEE 1547) is added only if the block itself is the interconnecting device. |
| **UL 1012** | Power units other than Class 2, input 600 V or less, AC or DC. [S] Commonly paired with CSA C22.2 No. 107.1 (power conversion equipment) for Canada. [S] | Plausible home for a general-purpose AC-to-AC converter with no distributed-energy role. No source confirmed an AC-to-AC unit listed this way. |
| **IEC 62477-1** | Safety of power electronic converter systems; the international reference. [2] | Needed for markets outside North America; worth designing to in parallel because its insulation and fault rules are close to the UL ones. [M] |
| **UL 1561 / UL 5085, UL 1446** | Dry-type and low-voltage transformers; insulation systems. [M] | Apply to L1, the EMI chokes, and (isolated block) the ferrite transformer as components. Not to the block as a whole. |
| **IEEE P3105** | "Recommended Practice for Design and Integration of Solid State Transformers in Electric Grid". An active project since 2021, not yet published. [S][2] | Watch it. It is a recommended practice aimed at grid-scale units, not a listing standard, but it is where solid-state-transformer language will first appear. |

Supporting standards a laboratory will pull in [M]: spacing (UL 840),
enclosures (UL 50/50E), plastics flammability (UL 94), surge protective
devices (UL 1449), fuses (UL 248), and for the protective electronics one of
the functional-safety documents below.

**Functional safety of the protection.** Electronic circuits and software that
are relied on for safety are evaluated for behaviour under faults. The usual
references are UL 991 (safety-related solid-state controls), UL 1998
(software) or UL 60730-1 Annex H, which grades functions by how much safety
depends on them and requires fault assessment of hardware and software. [S]
UL 1741 has carried functional-safety sections for specific functions. [S]
Which document a laboratory applies to this block I could not confirm.

## 4. Electrical code (NEC, NFPA 70)

No language specific to solid-state transformers was found in the code or in
commentary on the 2026 edition. [2] The existing rules that will be applied:

* **Listing and use per listing** (110.3). [M] The inspector accepts the
  block on the strength of its listing mark and installs it per its
  instructions. This is why section 3 matters more than anything here.
* **Autotransformer rules for the non-isolated block.** Sections 210.9 and
  215.11 require a circuit derived from an autotransformer to have a grounded
  conductor that is connected to the grounded conductor of the supply
  system. [2] The block's straight-through neutral is exactly that. It follows
  that both systems must be grounded wye with the neutral present, and that
  the block does not create a separately derived system. [2]
* **Overcurrent protection.** Section 450.4 covers autotransformers of 1000 V
  or less, with protection on the input side. [2] Because either port can be
  the input here, both are fused.
* **Isolated block.** It creates a separately derived system and is grounded
  and bonded as one (250.30). [M]
* **Disconnecting means.** The block is not one, with or without contactors;
  the upstream breaker is. [M]
* **Fault current.** Protection downstream must be coordinated with a source
  that delivers twice rated current, not twenty times. This is a site design
  issue but it must be stated on the nameplate and in the instructions. [M]

## 5. Emissions (FCC, 47 CFR Part 15 Subpart B)

* The block is an unintentional radiator and must be authorised before sale,
  by Supplier's Declaration of Conformity or certification. [S] Testing is
  required before issuing a declaration. [2]
* Class A limits apply to equipment for commercial and industrial
  environments and carry a mandatory user statement; Class B is for
  residential use and is stricter. [S]
* The exemptions in section 15.103 are narrow, and equipment with several
  devices is exempt only if every one of them qualifies. [S] I would not plan
  on an exemption.
* Conducted limits start at 150 kHz. [M] The switching frequency now ranges
  from 50 to about 110 kHz, so its second and third harmonics fall in the
  measured band at every load.
* Any radio added for monitoring (Wi-Fi, cellular) brings its own
  authorisation; use a pre-certified module. [M]

## 6. Others likely to be raised

* **Grid interconnection (IEEE 1547, UL 1741 SB).** Applies if the block is
  the point of interconnection for a source. If it sits between a listed
  inverter and the grid as a transformer would, the inverter carries that
  obligation, but a utility may ask how the block affects anti-islanding and
  ride-through. Raise it early. [M]
* **Harmonics (IEEE 519)** and **surge immunity (IEEE C62.41)**. [M]
* **Cybersecurity** for the remote monitoring interface (UL 2900 series,
  IEC 62443). [M]
* **Canada**: CSA C22.2 No. 107.1 for safety [S], ICES-003 for emissions [M].
* **International**: IEC 62477-1, the IEC 61000 series, CE marking. [2][M]

## 7. What the design has to do

| Requirement area | Design status | Action |
|---|---|---|
| Single-fault safety: series switch fails short | Two independent hardware trips and two crowbars, each able to clear the high-side fuse | Calculate crowbar and fuse coordination; show the 120 V side stays within a defined limit until the fuse clears |
| Single-fault safety: shunt switch fails short, output short, overload | Desaturation shutdown, fuses | Abnormal-operation tests; confirm no fire or shock hazard with the controller disabled |
| Loss of neutral | Detection added in revision E, not designed | Design and test; in a non-isolated block an open neutral can put the wrong voltage on the load |
| Software relied on for safety | Kept to a minimum; protection is hardware | Keep it that way. Every safety function moved into firmware adds evaluation effort |
| Insulation and spacing | 1200 V devices, 1.2 kV class layout assumed | Lay out to the working voltage, overvoltage category and pollution degree the laboratory assigns; no reinforced insulation is needed in the non-isolated block because it claims no isolation |
| Isolated block: reinforced insulation | 5.5 mm transformer barrier, reinforced drivers and sensors | Recognised insulation system in the transformer; partial-discharge and dielectric tests |
| Temperature rise | 10 kW continuous modelled; 20 kW for 10 s | Mark the short-time rating and its duty cycle on the nameplate; test both |
| No contactors | Removed | Mark "not a disconnecting means"; discharge the port capacitors to a safe voltage within the required time after the supply is opened |
| Autotransformer installation | Straight-through neutral | Instructions must require grounded wye systems with neutral on both sides |
| Limited fault current | 167 A | Nameplate and instructions; guidance on downstream protection |
| Emissions | Filter sized for 50 kHz fixed | Re-design for 50 to 110 kHz; pre-scan early, because the variable frequency moves energy across the start of the measured band |
| Efficiency claim | 99.21 % predicted | Measure at 35 % load at both ratios; decide which table row is being claimed |
| Monitoring interface | CAN FD and Ethernet, read-only by default | Authentication for anything that changes settings; firmware-update integrity |

## 8. Recommended next steps

1. **Book a preliminary design review with two testing laboratories** before
   any hardware is frozen. Ask each: which standard they would list it under
   (UL 1741 or UL 1012); which functional-safety document applies to the
   crowbar and shutdown circuits; whether removing the contactors is
   acceptable with duplicated over-voltage protection; and what they need to
   see for an autotransformer-type, non-isolated unit.
2. **Decide the product's role with respect to distributed energy.** It
   selects between the two listing routes and determines whether utility
   interconnection testing is in scope.
3. **Get a legal reading on the DOE definition** if the efficiency rule matters
   commercially, and decide which kVA row to design to. That choice is worth
   real money: 98.58 % and 99.06 % lead to different hardware.
4. **Obtain the standards themselves** (UL 1741, UL 1012, the current
   10 CFR 431.192 and 431.196, NEC 2023 or 2026) and check every [2] and [M]
   item in this document against them.
5. **Follow IEEE P3105.** Joining the working group is the direct way to see,
   and influence, the language that will later be cited for these products.

## 9. Sources

Regulation and standards bodies:
- [eCFR, 10 CFR 431.192 definitions](https://www.ecfr.gov/current/title-10/chapter-II/subchapter-D/part-431/subpart-K/section-431.192)
- [Federal Register, April 22 2024 final rule](https://www.federalregister.gov/documents/2024/04/22/2024-07480/energy-conservation-program-energy-conservation-standards-for-distribution-transformers)
- [Federal Register, June 15 2026 notice](https://www.federalregister.gov/documents/2026/06/15/2026-11971/energy-conservation-program-energy-conservation-standards-for-distribution-transformers)
- [DOE announcement of the request for information](https://www.energy.gov/cmei/articles/doe-issues-request-information-rfi-energy-conservation-standards-distribution)
- [Cornell LII, 10 CFR 431.196](https://www.law.cornell.edu/cfr/text/10/431.196)
- [UL standards catalogue, UL 1741](https://standardscatalog.ul.com/standards/en/standard_1741)
- [UL 1012 scope summary](https://standards.globalspec.com/std/14549389/ul-1012)
- [CSA C22.2 No. 107.1](https://www.csagroup.org/store/product/2425057/)
- [eCFR, 47 CFR 15.103](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-B/section-15.103)
- [Cornell LII, 47 CFR 15.101](https://www.law.cornell.edu/cfr/text/47/15.101)
- [Natural Resources Canada, dry-type transformers](https://natural-resources.canada.ca/energy-efficiency/energy-efficiency-regulations/dry-type-transformers)

Test laboratories:
- [UL Solutions, inverter and converter certification](https://www.ul.com/services/pv-inverter-certification)
- [Intertek, inverter and converter testing](https://www.intertek.com/energy-commodities/renewable/inverter-and-converter/)
- [Intertek, functional safety and UL 60730-1 Annex H](https://www.intertek.com/blog/2026/05-22-functional-safety-and-iecul-60730-1-annex-h/)

Secondary:
- [Maddox, 2029 efficiency tables](https://www.maddox.com/resources/articles/updated-doe-efficiency-standards)
- [Rex Power Magnetics, 2029 dry-type rules](https://www.rexpowermagnetics.com/knowledge-hub/doe-2029-efficiency-standards-for-dry-type-transformers-whats-changing-and-why-it-matters/)
- [Hammond, transformers exempt from the rule](https://americas.hammondpowersolutions.com/resources/faq/distribution-transformers/are-there-any-transformers-exempt-from-this-legislation)
- [mgrid, how a solid-state transformer gets certified](https://mgrid.org/2026/04/18/how-a-solid-state-transformer-gets-certified-ul-1741-iec-62109-ce-marking-and-the-path-to-a-us-utility-procurement-order/)
- [PSMA, recommended practices for solid-state transformer design and testing](https://www.psma.com/sites/default/files/uploads/node/8201/IS07_1%20Recommend%20Practices%20for%20Solid%20State%20Transformer%20and%20Design.pdf)
- [xgytek, solid-state transformer stages and testing](https://xgytek.com/blog/what-is-a-solid-state-transformer)
- [impedyme, solid-state transformer overview](https://impedyme.com/resource-center/solid-state-transformer/)
- [arXiv, From Grid to Chip](https://arxiv.org/pdf/2609.11649)
- [ECM, unconventional transformer connections](https://www.ecmweb.com/content/unconventional-transformer-connections-part-3)
- [Mike Holt forum, 210.9 / 215.11 autotransformer question](https://forums.mikeholt.com/threads/210-9-215-11-autotransformer-question.129119/latest)
- [Compliance Gate, FCC SDoC guide](https://compliancegate.com/fcc-sdoc)
