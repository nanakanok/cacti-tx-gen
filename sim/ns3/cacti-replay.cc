/*
 * cacti-replay.cc — replay a cacti-tx-gen OTG schedule in ns-3 and measure throughput.
 *
 * Mirrors the model emitted by `cacti-tx-gen convert-ns3`:
 *   - 2-node point-to-point link, DataRate = 2x peak slice rate, 1ms delay
 *   - one OnOffApplication per time slice (rate = slice rate, OnTime = slice duration,
 *     OffTime = 0), UDP or TCP, fixed packet size
 *   - PacketSink on the receiver
 *
 * Adds the measurement the generated script lacks: per-bin goodput at the sink and
 * per-bin wire rate at the receiving NetDevice, written to CSV.
 *
 * Schedule CSV input (no header): rate_bps,duration_sec
 */
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <fstream>
#include <iomanip>
#include <sstream>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("CactiReplay");

static uint64_t g_wireBytes = 0;   // cumulative bytes seen on the rx NetDevice (incl. headers)
static uint64_t g_wirePkts = 0;

static void
PhyRxEndTrace(Ptr<const Packet> p)
{
    g_wireBytes += p->GetSize();
    g_wirePkts += 1;
}

struct Slice
{
    double rateBps;
    double durationSec;
};

static std::vector<Slice>
ReadSchedule(const std::string& path)
{
    std::vector<Slice> sched;
    std::ifstream f(path);
    NS_ABORT_MSG_IF(!f.is_open(), "cannot open schedule file " << path);
    std::string line;
    while (std::getline(f, line))
    {
        if (line.empty() || line[0] == '#')
        {
            continue;
        }
        std::istringstream ss(line);
        std::string a, b;
        if (!std::getline(ss, a, ',') || !std::getline(ss, b, ','))
        {
            continue;
        }
        sched.push_back({std::stod(a), std::stod(b)});
    }
    return sched;
}

static std::ofstream g_out;
static uint64_t g_lastSinkBytes = 0;
static uint64_t g_lastWireBytes = 0;
static double g_lastT = 0.0;

static void
Sample(Ptr<PacketSink> sink, double interval)
{
    double now = Simulator::Now().GetSeconds();
    uint64_t sb = sink->GetTotalRx();
    double dt = now - g_lastT;
    if (dt > 0)
    {
        double goodput = (sb - g_lastSinkBytes) * 8.0 / dt;
        double wire = (g_wireBytes - g_lastWireBytes) * 8.0 / dt;
        g_out << std::fixed << std::setprecision(3) << now << "," << std::setprecision(1)
              << goodput << "," << wire << "\n";
    }
    g_lastSinkBytes = sb;
    g_lastWireBytes = g_wireBytes;
    g_lastT = now;
    Simulator::Schedule(Seconds(interval), &Sample, sink, interval);
}

int
main(int argc, char* argv[])
{
    std::string schedFile;
    std::string outFile = "cacti-replay.csv";
    std::string protocol = "udp";
    uint32_t packetSize = 1400;
    double sampleInterval = 0.0; // 0 => use slice duration
    double linkFactor = 2.0;
    std::string queueSize = "1000p";

    CommandLine cmd(__FILE__);
    cmd.AddValue("schedule", "schedule CSV: rate_bps,duration_sec per line", schedFile);
    cmd.AddValue("out", "output CSV path", outFile);
    cmd.AddValue("protocol", "udp or tcp", protocol);
    cmd.AddValue("packetSize", "application packet size in bytes", packetSize);
    cmd.AddValue("sampleInterval", "sampling interval in s (0 = slice duration)", sampleInterval);
    cmd.AddValue("linkFactor", "link speed = linkFactor * peak slice rate", linkFactor);
    cmd.AddValue("queueSize", "p2p device queue size", queueSize);
    cmd.Parse(argc, argv);

    std::vector<Slice> sched = ReadSchedule(schedFile);
    NS_ABORT_MSG_IF(sched.empty(), "empty schedule");

    double total = 0.0;
    double peak = 0.0;
    for (const auto& s : sched)
    {
        total += s.durationSec;
        peak = std::max(peak, s.rateBps);
    }
    if (sampleInterval <= 0.0)
    {
        sampleInterval = sched[0].durationSec;
    }
    uint64_t linkBps = static_cast<uint64_t>(peak * linkFactor);

    std::cout << "slices=" << sched.size() << " total=" << total << "s peak=" << peak / 1e9
              << "Gbps link=" << linkBps / 1e9 << "Gbps sample=" << sampleInterval << "s\n";

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", DataRateValue(DataRate(linkBps)));
    p2p.SetChannelAttribute("Delay", StringValue("1ms"));
    p2p.SetQueue("ns3::DropTailQueue<Packet>", "MaxSize", StringValue(queueSize));
    NetDeviceContainer devices = p2p.Install(nodes);

    InternetStackHelper stack;
    stack.Install(nodes);

    Ipv4AddressHelper addr;
    addr.SetBase("10.0.0.0", "255.255.255.0");
    Ipv4InterfaceContainer ifaces = addr.Assign(devices);

    uint16_t port = 12001;
    Address sinkAddr(InetSocketAddress(ifaces.GetAddress(1), port));
    std::string factory = (protocol == "tcp") ? "ns3::TcpSocketFactory" : "ns3::UdpSocketFactory";

    PacketSinkHelper sinkHelper(factory, InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApps = sinkHelper.Install(nodes.Get(1));
    sinkApps.Start(Seconds(0.0));
    sinkApps.Stop(Seconds(total + 1.0));
    Ptr<PacketSink> sink = DynamicCast<PacketSink>(sinkApps.Get(0));

    devices.Get(1)->TraceConnectWithoutContext("PhyRxEnd", MakeCallback(&PhyRxEndTrace));

    double t = 0.0;
    for (const auto& s : sched)
    {
        OnOffHelper onoff(factory, sinkAddr);
        onoff.SetAttribute("DataRate", DataRateValue(DataRate(static_cast<uint64_t>(s.rateBps))));
        onoff.SetAttribute("PacketSize", UintegerValue(packetSize));
        std::ostringstream on;
        on << "ns3::ConstantRandomVariable[Constant=" << s.durationSec << "]";
        onoff.SetAttribute("OnTime", StringValue(on.str()));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        ApplicationContainer app = onoff.Install(nodes.Get(0));
        app.Start(Seconds(t));
        app.Stop(Seconds(t + s.durationSec));
        t += s.durationSec;
    }

    g_out.open(outFile);
    g_out << "t,goodput_bps,wire_bps\n";
    Simulator::Schedule(Seconds(sampleInterval), &Sample, sink, sampleInterval);

    Simulator::Stop(Seconds(total + 1.0));
    Simulator::Run();

    std::cout << "sink_rx_bytes=" << sink->GetTotalRx() << " wire_bytes=" << g_wireBytes
              << " wire_pkts=" << g_wirePkts << "\n";
    std::cout << "goodput_avg_bps=" << sink->GetTotalRx() * 8.0 / total
              << " wire_avg_bps=" << g_wireBytes * 8.0 / total << "\n";

    Simulator::Destroy();
    g_out.close();
    return 0;
}
