from mininet.node import Host
from mininet.topo import Topo, SingleSwitchTopo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.link import Intf
from mininet.nodelib import NAT
from mininet.log import setLogLevel, info, error
from mininet.util import quietRun
from mininet.term import makeTerm

import sys
from functools import partial
import subprocess

SKEL = """from mininet.topo import Topo

class MyTopo( Topo ):

    def __init__( self ):
        Topo.__init__( self )
"""

class FabricCli(CLI):

    def do_vm_xterm(self, line):
        parts = line.split()
        if len(parts) == 2:
            c = self.mn[parts[0]]
            cmd = 'bash --init-file <(echo " exec ~/mininet/util/m %s-%s")' % (parts[0], parts[1])
            title = 'VM: %s / Node' % parts[1]
            self.mn.terms += makeTerm(c, cmd = cmd, title=title)
        else:
            error('Only two arguments to vm_xterm: vm_xterm c1 1-h1\n')

class PhysicalComputeNode( Host ):

    privateDirs = [ '/etc/openvswitch',
                    '/var/run/openvswitch',
                    '/var/log/openvswitch' ]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault( 'inNamespace', True )
        kwargs.setdefault( 'privateDirs', self.privateDirs )
        super( PhysicalComputeNode, self ).__init__( *args, **kwargs )

    def initNestedNet(self, config, controller = None):
        self.fd = open('/tmp/%s.py' % self.name, 'w')
        self.fd.write(SKEL)
        self.fd.write("        self.addSwitch('s1', dpid='%s')\n" % self.name)
        self.startOVS()

    def terminate(self):
        self.mn.terminate()
        self.stopOVS()

    def addHost(self, name, ip):
        self.fd.write('        self.addHost("%s", ip="%s")\n' % (name, ip))
        self.fd.write('        self.addLink("s1", "%s")\n' % name)

    def startOVS( self ):
        "Start new OVS instance"
        self.cmd( 'ovsdb-tool create /etc/openvswitch/conf.db' )
        self.cmd( 'ovsdb-server /etc/openvswitch/conf.db'
                  ' -vfile:emer -vfile:err -vfile:info'
                  ' --remote=punix:/var/run/openvswitch/db.sock '
                  ' --log-file=/var/log/openvswitch/ovsdb-server.log'
                  ' --pidfile=/var/run/openvswitch/ovsdb-server.pid'
                  ' --no-chdir'
                  ' --detach' )

        self.cmd( 'ovs-vswitchd unix:/var/run/openvswitch/db.sock'
                  ' -vfile:emer -vfile:err -vfile:info'
                  ' --mlockall --log-file=/var/log/openvswitch/ovs-vswitchd.log'
                  ' --pidfile=/var/run/openvswitch/ovs-vswitchd.pid'
                  ' --no-chdir'
                  ' --detach' )

    def stopOVS( self ):
        self.cmd( 'kill',
                  '`cat /var/run/openvswitch/ovs-vswitchd.pid`',
                  '`cat /var/run/openvswitch/ovsdb-server.pid`' )
        self.cmd( 'wait' )

    def runNet( self, ctrl ):
        self.fd.write("\ntopos = { 'mytopo': ( lambda: MyTopo() ) }\n")
        self.fd.close()
        if ctrl.lower() == 'none':
            self.mn = self.popen("mn --custom /tmp/%s.py --topo mytopo --controller none" % self.name,\
                                            stdin = subprocess.PIPE,\
                                            shell = True)
        else:
            ip,port = ctrl.split(':')
            self.mn = self.popen("mn --custom /tmp/%s.py --topo mytopo --controller remote,ip=%s,port=%s" % (self.name, ip, port),\
                                            stdin = subprocess.PIPE,\
                                            shell = True)


class Fabric( Topo ):

    def build( self, config):
        #TODO Integrate segment routing
        self.sws = {}
        self.sws['fabric'] = self.addSwitch( 'fabric', dpid='0000000000000001' )
        self.mgmtSw = self.constructMgmtNet()
        self.constructPhysicalNodes(config['physical-nodes'])

    def constructPhysicalNodes(self, physConfig):
        for (i, name) in enumerate(physConfig.keys()):
            host = self.addHost(name, ip = physConfig[name]['ip'], cls=PhysicalComputeNode)
            self.addLink(host, self.sws[physConfig[name]['location']], intfName1 = '%s-eth0' % name )
            self.addLink(host, self.mgmtSw, intfName1 = 'mgmt', params1 = { 'ip' : '192.168.254.%s/24' % (i + 2) }  )

    def constructMgmtNet(self):
        mgmtSw = self.addSwitch( 'mgmtSw', dpid = '0000000000000002', failMode = 'standalone' )
        nat = self.addHost("nat", ip = '192.168.254.1/24', cls = NAT, subnet = '192.168.254.0/24', inNamespace = False)
        self.addLink(nat, mgmtSw)
        return mgmtSw


def setController(ctrl):
    if ctrl.lower() == 'none':
        quietRun('ovs-ofctl add-flow fabric actions=normal')
    else:
        quietRun('ovs-vsctl set-controller fabric ctrl')

def configureVirtualNets(net, nets):
    for i,data in enumerate(nets):
        if data['location'] == 'colocated':
            assert data['node'] in net, "%s is not a compute node" % data['node']
            for j in range(1,int(data['virtual-nodes']) + 1):
                net[data['node']].addHost('%s-%s-h%s' % (data['node'], i+1, j), ip = "10.0.0.%s/24" % j)
        elif data['location'] == 'custom':
            num_nodes = data['virtual-nodes']
            node_map = data['nodes']
            assert num_nodes == sum(node_map.values()), "Custom mapping does not match total num of vms"
            for (node, num) in node_map.iteritems():
                assert node in net, "%s is not a compute node" % node
                for j in range(1, int(num) + 1):
                    net[node].addHost('%s-%s-h%s' % (node, i+1, j), ip = "10.0.0.%s/24" % j)
        else:
            error('Unknown vnet location %s\n' % data['location'])

if __name__ == '__main__':
    import json
    setLogLevel( 'info' )
    with open('fabric.json') as data_file:
        config = json.load(data_file)

    net = Mininet( topo = Fabric(config), controller = None )
    net.start()
    setController(config['controller'])
    for i,host in enumerate(net.hosts):
        if isinstance(host, PhysicalComputeNode):
            host.initNestedNet(None)
            host.setDefaultRoute(intf = 'dev mgmt via 192.168.254.1')
            host.cmd("ovs-appctl -t ovsdb-server ovsdb-server/add-remote ptcp:6640:%s" % host.IP(intf = "mgmt"))
            net['nat'].cmd("iptables -t nat -A PREROUTING -p tcp --dport %s -j DNAT --to %s:6640" % (6641+i, host.IP(intf = "mgmt")))
            info('Node %s has ovsdb on local port %s\n' % (host, 6641+i))
    configureVirtualNets(net, config['virtual-nets'])
    for host in net.hosts:
        if isinstance(host, PhysicalComputeNode):
            host.runNet(config['controller'])
    FabricCli( net )
    net.stop()
