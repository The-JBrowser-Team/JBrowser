"""Built-in third-party blocklist: ad networks, trackers, fingerprinters, cryptominers, telemetry.

Entries are registrable domains or hostnames; any sub-domain matches. The list can be
extended at runtime with hosts-format or Adblock-style ``||domain^`` lists
(Settings → Privacy → Update blocklist).
"""

ADS = """
doubleclick.net googlesyndication.com googleadservices.com adservice.google.com pagead2.googlesyndication.com
tpc.googlesyndication.com imasdk.googleapis.com googletagservices.com adnxs.com adnxs-simple.com
rubiconproject.com pubmatic.com openx.net casalemedia.com indexww.com advertising.com adsrvr.org
criteo.com criteo.net taboola.com outbrain.com outbrainimg.com revcontent.com mgid.com zergnet.com
media.net contextweb.com sovrn.com lijit.com 33across.com sharethrough.com smartadserver.com yieldmo.com
teads.tv zemanta.com triplelift.com 3lift.com gumgum.com undertone.com spotxchange.com spotx.tv
springserve.com adform.net serving-sys.com sizmek.com flashtalking.com innovid.com tremorhub.com
yahoo-ads.com ads.yahoo.com advertising.yahoo.com adtech.com adtechus.com bidswitch.net
mathtag.com turn.com amazon-adsystem.com aax.amazon-adsystem.com media6degrees.com simpli.fi
districtm.io onetag-sys.com yieldlab.net improvedigital.com adition.com smaato.net inmobi.com
applovin.com unityads.unity3d.com vungle.com chartboost.com admob.com adcolony.com ironsrc.com
popads.net popcash.net propellerads.com adsterra.com exoclick.com juicyads.com trafficjunky.net
hilltopads.net clickadu.com adcash.com admaven.com a-ads.com bidvertiser.com infolinks.com
buysellads.com carbonads.net servedby-buysellads.com adroll.com nextroll.com perfectaudience.com
quantcast.com quantserve.com rlcdn.com liveramp.com pippio.com adsafeprotected.com
moatads.com moat.com doubleverify.com iasds01.com adlightning.com confiant-integrations.net
ad.doubleclick.net securepubads.g.doubleclick.net ads.linkedin.com ads.pinterest.com ads-twitter.com
static.ads-twitter.com ads.tiktok.com ads.reddit.com adsymptotic.com adhigh.net lkqd.net
"""

TRACKERS = """
google-analytics.com analytics.google.com ssl.google-analytics.com googletagmanager.com
stats.g.doubleclick.net app-measurement.com firebaselogging-pa.googleapis.com
connect.facebook.net pixel.facebook.com an.facebook.com facebook.com/tr graph.instagram.com
scorecardresearch.com comscore.com sb.scorecardresearch.com chartbeat.com chartbeat.net
hotjar.com hotjar.io mouseflow.com crazyegg.com luckyorange.com luckyorange.net fullstory.com
logrocket.com logrocket.io smartlook.com inspectlet.com clicktale.net contentsquare.net
clarity.ms c.clarity.ms bat.bing.com mixpanel.com mxpnl.com api-js.mixpanel.com cdn.segment.com
api.segment.io segment.io amplitude.com api.amplitude.com cdn.amplitude.com heap.io heapanalytics.com
kissmetrics.com kissmetrics.io woopra.com statcounter.com histats.com hitslink.com
snap.licdn.com px.ads.linkedin.com analytics.tiktok.com analytics.twitter.com t.co/i/adsct
ct.pinterest.com trk.pinterest.com analytics.pinterest.com sc-static.net tr.snapchat.com
analytics.yahoo.com sp.analytics.yahoo.com mc.yandex.ru mc.yandex.com hm.baidu.com cnzz.com
bluekai.com krxd.net demdex.net omtrdc.net 2o7.net everesttech.net exelator.com eyeota.net
tapad.com agkn.com crwdcntrl.net lotame.com adsymptotic.com dotomi.com emxdgt.com bounceexchange.com
wunderkind.co tealiumiq.com tiqcdn.com ensighten.com optimizely.com cdn.optimizely.com
newrelic.com nr-data.net js-agent.newrelic.com bam.nr-data.net branch.io app.link adjust.com
appsflyer.com kochava.com singular.net mparticle.com braze.com appboy.com iterable.com
parsely.com parse.ly pixel.wp.com stats.wp.com quantcount.com addthis.com addthisedge.com
sharethis.com po.st gigya.com
omnitagjs.com permutive.com permutive.app id5-sync.com liadm.com rfihub.com
zeotap.com adsafety.net iponweb.net bidr.io sonobi.com yieldoptimizer.com
cdn.heapanalytics.com piwik.pro matomo.cloud plausible.io/api stats.pusher.com
"""

MINERS = """
coinhive.com coin-hive.com authedmine.com crypto-loot.com cryptoloot.pro coinimp.com jsecoin.com
minero.cc webmine.pro webminepool.com monerominer.rocks ppoi.org coinerra.com cryptonoter.com
coinblind.com minemytraffic.com hashing.win jscoinminer.com projectpoi.com minr.pw deepminer.net
mineralt.io kickass.cd/miner miner.pr0gramm.com coin-have.com gridcash.net
"""

TELEMETRY = """
sentry.io ingest.sentry.io browser.sentry-cdn.com bugsnag.com sessions.bugsnag.com notify.bugsnag.com
rollbar.com api.rollbar.com raygun.io trackjs.com loggly.com datadoghq-browser-agent.com
browser-intake-datadoghq.com rum.browser-intake-datadoghq.com dc.services.visualstudio.com
vortex.data.microsoft.com telemetry.microsoft.com watson.telemetry.microsoft.com
events.data.microsoft.com mobile.events.data.microsoft.com browser.events.data.msn.com
telemetry.mozilla.org incoming.telemetry.mozilla.org stats.mozilla.org
beacons.gcp.gvt2.com beacons.gvt2.com clientservices.googleapis.com/uma
speedcurve.com lux.speedcurve.com mpulse.akamai.com go-mpulse.net
"""


def builtin_rules() -> tuple[set[str], dict[str, list[str]]]:
    """Return (blocked domains, {host: [blocked path prefixes]})."""
    domains: set[str] = set()
    paths: dict[str, list[str]] = {}
    for block in (ADS, TRACKERS, MINERS, TELEMETRY):
        for token in block.split():
            token = token.strip().lower()
            if not token:
                continue
            if "/" in token:
                host, path = token.split("/", 1)
                paths.setdefault(host, []).append("/" + path)
            else:
                domains.add(token)
    return domains, paths


CATEGORIES = {
    "ads": ADS, "trackers": TRACKERS, "miners": MINERS, "telemetry": TELEMETRY,
}
