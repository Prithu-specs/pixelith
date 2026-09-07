# Pixelith licensing

Pixelith is **source-available, not open source**. PGA Tech Solutions publishes
the source so people can inspect, learn from and modify the software for their
own permitted use. The rights to use it come from the
[Pixelith End User Licence Agreement 1.0](../LICENSE), not from an open-source
licence.

> **Public beta: free and unlimited until 5 December 2026.** Personal and
> commercial use are both permitted during the beta. There is no payment step,
> no subscription and no retrospective charge for work produced during the
> beta.

The public beta began on 4 September 2026. Usage is counted locally and free
output carries the disclosed provenance mark, but neither limits permitted use
during the beta. The post-beta terms below begin on 5 December 2026.

## After the public beta

| Tier | India | Outside India | What it covers |
|---|---:|---:|---|
| **Free** | Rs 0 | Rs 0 | Personal use within 100 still images and 1 GB of video input |
| **Personal** | Rs 513 + GST (Rs 605 total at 18%) | US$10 + applicable local tax | One named person, any devices they own or personally control, unlimited use, one-time payment |
| **Commercial** | Rs 8,228 + GST (Rs 9,709 total at 18%) | US$200 + applicable local tax | One legal entity, its staff and contractors, any number of seats, unlimited business and client use, one-time payment |

Paid licences are perpetual for the purchased version series and later releases
made available under the same terms. They do not expire and have no renewal or
subscription fee. A paid licence also removes the free-output provenance mark.

The Free Tier's image and video allowances are independent. Charities, schools,
colleges, universities, public research bodies, public health or safety
organisations, and government bodies are treated as Personal Use for their own
non-revenue purposes. Commercial use after the beta requires a Commercial
Licence from the first byte; there is no free commercial allowance.

A Commercial Licence covers using Pixelith to produce work. Redistributing,
reselling, sublicensing or hosting Pixelith as a product or service requires
separate written permission from PGA Tech Solutions.

## Privacy, local verification and the free-output mark

Pixelith processes your photos and videos locally. It does not upload your
media, use it to train AI, require an account, send telemetry or report usage to
PGA Tech Solutions. Its only network access is the first-run download of model
weights from a public host.

Free-tier allowances are measured in a usage record stored on your own machine.
Licence keys are Ed25519-signed and verified offline against a public key built
into the app; there is no activation server.

Free-tier output contains an invisible, machine-readable provenance mark that
identifies the tier, installation and allowance position. It contains no name,
file contents, location or other personal information, and it is never
transmitted. Output made under a Personal or Commercial Licence carries no
mark. See clauses 7.1–7.8 of the EULA for the complete terms.

## Pricing, tax and seller details

Pixelith is made by **PGA Tech Solutions**, a sole proprietorship in Uttar
Pradesh, India (GSTIN `09AIAPG7383C1ZE`). Indian prices exclude GST; the current
stated rate is 18% for software licensing services under SAC 997331, and the
all-in amount is shown before purchase. A tax invoice is issued for Indian
sales. Supplies to buyers outside India are described in the EULA as exports of
service supplied under Letter of Undertaking without payment of IGST; applicable
local tax may be added by the merchant of record.

## Versions and third-party components

Pixelith versions 0.1.x remain under the
[PolyForm Noncommercial License 1.0.0](../LICENSE-0.1.x-PolyForm-Noncommercial-1.0.0.txt).
The Pixelith EULA applies to version 0.2.0 and later.

The EULA covers Pixelith's own engine, pipeline, server, interface and tooling.
Third-party components—including model weights, ONNX Runtime, FFmpeg and Python
libraries—remain under their own licences. See [NOTICE.md](../NOTICE.md).

## Questions and purchases

Email [licensing@pgatech.solutions](mailto:licensing@pgatech.solutions). For a
commercial enquiry, say whether you only need to run Pixelith or also need
redistribution, resale or hosted-service rights.

---

This page is a plain-English convenience summary, not a substitute for the
[Pixelith End User Licence Agreement 1.0](../LICENSE). If this page and the EULA
differ, the EULA controls. It is not legal or tax advice. Beta terms are
effective from 4 September 2026; post-beta pricing is scheduled from
5 December 2026. Current release: Pixelith v0.40b4.
