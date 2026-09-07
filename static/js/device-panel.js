const devicePanel = (() => {
  const panel = document.getElementById("device-panel");
  const body = document.getElementById("device-panel-body");
  const stamp = document.getElementById("device-stamp");
  const toggleBtn = document.getElementById("btn-toggle-device");

  function esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  function fmtBytes(n) {
    if (n === null || n === undefined) return null;
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let val = n;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(val >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function fmtRate(bps) {
    if (bps === null || bps === undefined) return null;
    return `${fmtBytes(bps)}/s`;
  }

  function fmtMs(ms) {
    return ms === null || ms === undefined ? null : `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;
  }

  function fmtUptime(seconds) {
    if (seconds === null || seconds === undefined) return null;
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  /** One "key ....... value" line plus the short description under it. */
  function kv(key, value, hint, tone = "") {
    const missing = value === null || value === undefined || value === "";
    const shown = missing ? "n/a" : value;
    const cls = missing ? "na" : tone;
    return `
      <div class="kv">
        <div class="kv-line">
          <span class="kv-key">${esc(key)}</span>
          <span class="kv-fill"></span>
          <span class="kv-val ${cls}">${esc(shown)}</span>
        </div>
        <span class="kv-hint">${hint}</span>
      </div>`;
  }

  function block(title, desc, rows) {
    return `
      <div class="status-block">
        <h3>${esc(title)}</h3>
        <p class="block-desc">${desc}</p>
        ${rows.join("")}
      </div>`;
  }

  function tri(v, yes, no) {
    if (v === null || v === undefined) return { text: null, tone: "" };
    return v ? { text: yes, tone: "ok" } : { text: no, tone: "bad" };
  }

  function render(data) {
    const {
      host,
      ipv4,
      ipv6,
      dns,
      interface: iface,
      wifi,
      traffic,
      public: pub,
      connectivity,
    } = data;

    const ifaceUp = tri(iface.isup, "up", "down");
    const gw = connectivity.gateway || {};
    const net = connectivity.internet || {};
    const gwReach = tri(gw.reachable, "reachable", "unreachable");
    const netReach = tri(net.reachable, "online", "offline");
    const dnsOk = tri(dns.test?.success, "ok", "failed");
    const vpn = connectivity.vpn_or_proxy || {};

    const errors = (traffic.errin ?? 0) + (traffic.errout ?? 0);
    const drops = (traffic.dropin ?? 0) + (traffic.dropout ?? 0);
    const hasTraffic = Object.keys(traffic || {}).length > 0;

    const blocks = [];

    blocks.push(
      block("machine", "The host this monitor is running on.", [
        kv("hostname", host.hostname, "Name this machine answers to on the local network."),
        kv("os", host.os, "Operating system and release the checks are running under."),
        kv("uptime", fmtUptime(host.uptime_s), "Time since last boot. A recent reboot explains counters starting from zero."),
        kv("dns suffix", host.dns_suffix, "Domain automatically appended to unqualified hostnames, if the network sets one."),
      ])
    );

    blocks.push(
      block("connectivity", "Does traffic actually get out, and how far.", [
        kv(
          "gateway",
          gwReach.text ? `${gwReach.text}${fmtMs(gw.latency_ms) ? ` · ${fmtMs(gw.latency_ms)}` : ""}` : null,
          `TCP probe against the router. Unreachable means the fault is local, before the internet.${
            gw.detail ? ` Last probe: ${esc(gw.detail)}.` : ""
          }`,
          gwReach.tone
        ),
        kv(
          "internet",
          netReach.text ? `${netReach.text}${fmtMs(net.latency_ms) ? ` · ${fmtMs(net.latency_ms)}` : ""}` : null,
          `Probe to <code>${esc(net.probe || "an external host")}</code>, past your router. Up here with a dead gateway is impossible; the reverse means your ISP is the problem.`,
          netReach.tone
        ),
        kv(
          "vpn / proxy",
          vpn.suspected === null || vpn.suspected === undefined
            ? null
            : vpn.suspected
            ? "suspected"
            : "none detected",
          vpn.reasons && vpn.reasons.length
            ? `Heuristic. Signals seen: ${esc(vpn.reasons.join("; "))}.`
            : "Heuristic based on adapter names, proxy environment variables and who owns your public IP. Not proof either way.",
          vpn.suspected ? "warn" : ""
        ),
      ])
    );

    blocks.push(
      block(
        "public identity",
        pub && pub.enabled === false
          ? "Turned off, so nothing leaves your network."
          : "How the internet sees you &mdash; read via one outbound request.",
        pub && pub.enabled === false
          ? [kv("lookup", "disabled", "Set <code>TP_PUBLIC_IP_LOOKUP=1</code> to enable it.")]
          : pub && pub.error
          ? [kv("lookup", "failed", `Could not reach the lookup service: ${esc(pub.error)}.`, "bad")]
          : [
              kv("public ip", pub?.ip, "Address every server on the internet sees your traffic coming from. Not your LAN address above."),
              kv("reverse dns", pub?.hostname, "Name your ISP has registered for that address, when it publishes one."),
              kv("network", pub?.org, "The autonomous system that owns the address &mdash; normally your ISP, or your VPN provider if one is on."),
              kv("geo", pub?.location, "Where the address is registered. Approximate, and often only accurate to the city."),
              kv("timezone", pub?.timezone, "Timezone associated with that address; a mismatch with your own is a sign of a VPN exit."),
            ]
      )
    );

    blocks.push(
      block("ipv4", "This machine&rsquo;s IPv4 identity on the local network.", [
        kv("address", ipv4.address, "The address this machine holds on the active network."),
        kv("subnet mask", ipv4.netmask, "Which part of the address is the network &mdash; it defines who counts as a local neighbour."),
        kv("network", ipv4.cidr, "The same subnet in CIDR form: the range of addresses reachable without the router."),
        kv("gateway", ipv4.gateway, "The router every packet bound for the internet is handed to."),
        kv("dhcp", ipv4.dhcp, "Whether the address was leased automatically or set by hand."),
        kv("dhcp server", ipv4.dhcp_server, "Which device handed out the lease &mdash; normally the router."),
        kv("lease expires", ipv4.lease_expires, "When the address must be renewed. Usually invisible; matters when addresses start changing."),
      ])
    );

    blocks.push(
      block("ipv6", "IPv6 addressing, if the network hands any out.", [
        kv(
          "routable",
          (ipv6.addresses || []).join(", "),
          "Globally routable IPv6 addresses. Empty means this network is IPv4-only, which is normal on many home connections."
        ),
        kv(
          "link-local",
          ipv6.link_local,
          "An <code>fe80::</code> address that works only on the local link. Present whenever IPv6 is enabled at all."
        ),
      ])
    );

    blocks.push(
      block("dns", "Name resolution &mdash; how hostnames become addresses.", [
        kv(
          "servers",
          (dns.servers || []).join(", "),
          "Resolvers this adapter is configured to ask. A <code>127.x</code> address means a resolver running on this machine (Pi-hole, AdGuard, a VPN client) is intercepting lookups first."
        ),
        kv(
          "lookup test",
          dnsOk.text
            ? `${dnsOk.text}${fmtMs(dns.test?.latency_ms) ? ` · ${fmtMs(dns.test.latency_ms)}` : ""}`
            : null,
          `A live resolution of <code>${esc(dns.test?.host || "a known host")}</code>${
            dns.test?.resolved?.length ? `, which returned ${esc(dns.test.resolved.join(", "))}` : ""
          }. Failure means DNS is broken even when the link itself is up.`,
          dnsOk.tone
        ),
      ])
    );

    blocks.push(
      block("interface", "The network adapter currently carrying traffic.", [
        kv("name", iface.name, "Adapter chosen as active &mdash; the one holding the default gateway."),
        kv("hardware", iface.description, "The physical device or driver behind that adapter."),
        kv("mac", iface.mac, "Hardware address of the adapter, unique to the NIC."),
        kv("state", ifaceUp.text, "Whether the operating system reports the link as up.", ifaceUp.tone),
        kv("link speed", iface.speed_mbps ? `${iface.speed_mbps} Mbps` : null, "Negotiated link rate reported by the driver &mdash; the ceiling, not measured throughput."),
        kv("duplex", iface.duplex, "Full duplex sends and receives at once. Half duplex on a modern link points at a negotiation fault."),
        kv("mtu", iface.mtu, "Largest packet the link accepts before it has to be fragmented."),
      ])
    );

    if (wifi) {
      blocks.push(
        block("wireless", "Radio detail for the wireless link.", [
          kv("ssid", wifi.ssid, "The network name this adapter is associated with."),
          kv("bssid", wifi.bssid, "MAC address of the specific access point you are on &mdash; useful when roaming between several."),
          kv("signal", wifi.signal, "Signal strength as a percentage. Below roughly 50% expect retransmits and jitter."),
          kv("radio", wifi.radio, "802.11 generation in use, e.g. 802.11ax is Wi-Fi 6."),
          kv("band / channel", [wifi.band, wifi.channel].filter(Boolean).join(" · "), "Frequency band and channel. A crowded 2.4 GHz channel is a common cause of erratic latency."),
          kv("rate rx / tx", [wifi.rx_mbps, wifi.tx_mbps].filter(Boolean).join(" / "), "Currently negotiated receive and transmit rates in Mbps."),
          kv("security", wifi.auth, "Authentication in use on this network."),
        ])
      );
    }

    blocks.push(
      block(
        "traffic",
        "Counters for the active adapter, cumulative since boot, plus the live rate.",
        hasTraffic
          ? [
              kv(
                "rate down / up",
                fmtRate(traffic.recv_rate_bps) && fmtRate(traffic.send_rate_bps)
                  ? `${fmtRate(traffic.recv_rate_bps)} / ${fmtRate(traffic.send_rate_bps)}`
                  : null,
                "Throughput measured between the last two snapshots. Refresh twice to see a figure."
              ),
              kv(
                "total down / up",
                `${fmtBytes(traffic.bytes_recv)} / ${fmtBytes(traffic.bytes_sent)}`,
                "Total bytes in and out over this interface since the machine booted."
              ),
              kv(
                "packets in / out",
                `${traffic.packets_recv ?? "n/a"} / ${traffic.packets_sent ?? "n/a"}`,
                "Packet counts in each direction, regardless of size."
              ),
              kv(
                "errors / drops",
                `${errors} / ${drops}`,
                "Malformed packets and packets discarded. Numbers that climb steadily point at a bad cable, a failing NIC, or a saturated link.",
                errors + drops > 0 ? "warn" : "ok"
              ),
            ]
          : [kv("counters", null, "No per-interface counters are available for the active adapter.")]
      )
    );

    body.innerHTML = `<div class="status-grid">${blocks.join("")}</div>`;

    const readAt = data.read_at ? new Date(data.read_at * 1000) : new Date();
    stamp.textContent = `read ${readAt.toLocaleTimeString()}`;
    stamp.classList.remove("stamp-flash");
    void stamp.offsetWidth; // restart the flash animation
    stamp.classList.add("stamp-flash");
  }

  function showLoading() {
    body.innerHTML = `<p class="muted loading"><span class="spinner"></span> reading interfaces</p>`;
    stamp.textContent = "";
  }

  function showError(message) {
    body.innerHTML = `<div class="form-error">${esc(message)}</div>`;
    stamp.textContent = "read failed";
  }

  toggleBtn.addEventListener("click", () => {
    const collapsed = body.hidden;
    body.hidden = !collapsed;
    toggleBtn.querySelector("i").className = collapsed ? "bi bi-chevron-up" : "bi bi-chevron-down";
    toggleBtn.setAttribute("aria-label", collapsed ? "Collapse device status" : "Expand device status");
  });

  return { render, showLoading, showError };
})();
