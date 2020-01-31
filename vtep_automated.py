# Script to configure VXLAN MP-BGP EVPN Leaf Switches.
# This is the work of a few days just to understand some basic structures of Python and how to utiilize them
# to interact with Nexus boxes. VXLAN EVPN with MP-BGP Overlay and OSPF Underlay is involving too many keystrokes
# and repetitive configurations on many devices.
# The script uses ip unnumbered interfaces between leaves and spines so i suggest to look for it if you are not familiar.
# This basic script is the result of a week long Python self-study.
# I'm %100 sure that there are a lot to improve.

from netmiko import ConnectHandler
from netmiko.cisco import CiscoNxosSSH
from netmiko.ssh_exception import NetMikoTimeoutException
from paramiko.ssh_exception import SSHException
from netmiko.ssh_exception import AuthenticationException
from getpass import getpass
import paramiko
import time

username = 'admin'
password = getpass()

DEVICE_LIST = open('vtep_device_list.txt')
for DEVICE in DEVICE_LIST:
    DEVICE = DEVICE.strip()

    N9K = {
    'ip':   DEVICE,
    'username': 'admin',
    'password': password ,
    'device_type': 'cisco_nxos',
    }
    print ('\n #### Connecting to the '  + DEVICE + ' ' + '#### \n' )

    try:
        net_connect = ConnectHandler(**N9K)
    except NetMikoTimeoutException:
        print ('\n #### Device not reachable #### \n')
        continue
    except AuthenticationException:
        print ('\n #### Authentication Failure #### \n')
        continue
    except SSHException:
        print ('\n #### Check to see if SSH is enabled on device #### \n')
        continue

    print ('\n #### Connection successfull, enabling VXLAN related features... #### \n')

    features = [ 'feature ospf', 
                    'feature bgp',
                    'feature pim',
                    'feature nv overlay',
                    'feature interface-vlan',
                    'nv overlay evpn',
                    'feature vn-segment-vlan-based' ]
    net_connect.send_config_set(features)
    #
    output=net_connect.send_command('show run | i feature')
    print(output)
    time.sleep(2)
    print ('\n #### Features are successfully enabled #### \n')

    VTEP_IP_LIST = open('vtep_ip_list.txt') 
    for line in VTEP_IP_LIST:
        line_fields = line.split()
        hostname = line_fields[0]
        ip_1 = line_fields[1]
        ip_2 = line_fields[2]
        if hostname == DEVICE:
            vtep_ip_config = ['interface loopback 0',
                                'ip address' + ' ' + ip_1  +'/32',
                                'description VTEP_IP_Address',
                                'ip router ospf vxlan_underlay area 0.0.0.0',
                                'ip pim sparse-mode' ]
            net_connect.send_config_set(vtep_ip_config)
            print('\n #### VTEP IP Address is configured on Loopback 0 #### \n')
            time.sleep(2)

            numbered_ip_config = ['interface loopback 100',
                                    'ip address' + ' ' + ip_2  +'/32',
                                    'description Numbered_interface_ip_to_be_used_on_p2p_links',
                                    'ip router ospf vxlan_underlay area 0.0.0.0',
                                    'ip pim sparse-mode' ]
            net_connect.send_config_set(numbered_ip_config)
            print('\n #### Numbered IP Address is configured on Loopback 100 #### \n')
            time.sleep(2)

            print('\n #### Creating named OSPF process #### \n')
            ospf_underlay_config = ['router ospf vxlan_underlay',
                                    'router-id' +' '+ ip_2,
                                    'log-adjacency-changes',
                                    'vrf tenant-vrf-100' ]
            net_connect.send_config_set(ospf_underlay_config)
            print("\n #### OSPF Process 'vxlan_underlay' created #### \n")
            time.sleep(2)

            print('\n #### Creating BGP Process #### \n')
            bgp_router_id_config = ['router bgp 65001',
                                    'router-id' +' '+ ip_2, ]
            net_connect.send_config_set(bgp_router_id_config)
            print('\n #### BGP Process created #### \n')
            time.sleep(2)

    print('\n #### Configuring Spine facing interfaces #### \n')
    time.sleep(2)

    spine_int_config = ['interface ethernet 1/1-2',
                            'no switchport',
                            'mtu 9216',
                            'medium p2p',
                            'ip ospf network point-to-point',
                            'ip router ospf vxlan_underlay area 0.0.0.0',
                            'ip pim sparse-mode',
                            'ip unnumbered loopback 100',
                            'no shutdown' ]
    net_connect.send_config_set(spine_int_config)
    output = net_connect.send_command('show run int eth 1/1-2 \n')
    print(output)
    time.sleep(3)

    print('\n #### Spine facing interfaces are configured #### \n')
    time.sleep(6) # Giving some time to OSPF to form up.

    output = net_connect.send_command('show ip ospf neighbors')
    print(output)
    time.sleep(3)

    print('\n #### Verifying PIM RP Address Reachability #### \n')
    output = net_connect.send_command('show ip route 1.1.1.190')
    print(output)
    time.sleep (2)

    print('\n #### Configuring PIM Anycast RP Address on VTEP #### \n')
    pim_config = ['ip pim rp-address 1.1.1.190 group-list 225.12.0.0/16',
                    'ip pim ssm range 232.0.0.0/8']
    net_connect.send_config_set (pim_config)
    output = net_connect.send_command ('show ip pim rp')
    print(output)
    time.sleep(2)

    print('\n #### Configuring BGP related settings #### \n')
    SPINE_IP_LIST = open('spine_ip_list.txt')
    for line in SPINE_IP_LIST:
        line_fields = line.split()
        spine_ip = line_fields[2]

        bgp_overlay_config = ['router bgp 65001',
                                'neighbor' + ' ' + spine_ip + ' ' + 'remote-as 65001',
                                'update-source loopback 100',
                                'address-family ipv4 unicast',
                                'send-community both',
                                'address-family l2vpn evpn',
                                'send-community both',
                                 ]
        net_connect.send_config_set(bgp_overlay_config)

    bgp_vrf_config = ['router bgp 65001',
                        'vrf tenant-vrf-100'
                        'address-family ipv4 unicast']
    net_connect.send_config_set(bgp_vrf_config)
    output = net_connect.send_command('show run bgp')
    print(output)
    time.sleep(3)
    print('\n #### Verifying IPv4 Capabilities with Spines #### \n')
    time.sleep(5)
    output1 = net_connect.send_command('show ip bgp summary')
    print(output1)
    time.sleep(5)
    print('\n #### Verifying L2VPN EVPN Capabilities with Spines #### \n')
    time.sleep(3)
    output2 = net_connect.send_command('show bgp l2vpn evpn summary')
    print(output2)
    time.sleep(5)

    print('\n #### Configuring L3VNI, Tenant VRF and L3 interface for Inter-VXLAN Routing #### \n')

    l3_vni_config = ['vlan 100',
                        'vn-segment 10100',
                        'exit',
                        'vrf context tenant-vrf-100',
                        'vni 10100',
                        'rd auto',
                        'address-family ipv4 unicast',
                        'route-target both auto',
                        'route-target both auto evpn']
    net_connect.send_config_set(l3_vni_config)

    l3_int_config = ['interface vlan 100',
                        'vrf member tenant-vrf-100',
                        'ip forward',
                        'no shutdown']
    net_connect.send_config_set(l3_int_config)


    print('\n #### Verifying L3 VNI Interface Configuration #### \n')
    output = net_connect.send_command('show run interface vlan 100')
    print(output)
    time.sleep(2)

    print('\n #### Creating L2 VNIs and adding them to the EVPN #### \n')
    for x in range (21,30):
        l2_vni_config = ['vlan' + ' ' + str(x),
                            'vn-segment 100'+str(x),
                            'exit',
                            'evpn',
                            'vni 100'+str(x) + ' ' + 'l2',
                            'rd auto',
                            'route-target import auto',
                            'route-target export auto']
        net_connect.send_config_set(l2_vni_config)

    output = net_connect.send_command ('show vxlan')
    print(output)
    time.sleep(5)
    output = net_connect.send_command ('show run bgp | grep evpn')
    print(output)
    time.sleep(2)

    print('\n #### Configuring Anycast Gateway MAC Address #### \n')
    time.sleep(2)
    anycast_mac = ['fabric forwarding anycast-gateway-mac 1111.2222.3333']
    net_connect.send_config_set(anycast_mac)

    output = net_connect.send_command('show run fabric forwarding')
    print(output)
    time.sleep(2)

    print('\n #### Creating  VXLAN Tunnel Interface "nve 1" #### \n')
    time.sleep(2)

    for x in range (21,30):
        nve_int_config = ['interface nve 1',
                            'no shutdown',
                            'source-interface loopback 0',
                            'host-reachability protocol bgp',
                            'member vni 10100 associate-vrf',
                            'member vni 100'+str(x),
                            'mcast-group 225.12.0.'+str(x),
                            ]
        net_connect.send_config_set(nve_int_config)

    output = net_connect.send_command('show int nve 1')
    print(output)
    time.sleep(3)

    print('\n #### Creating SVIs necessary for server traffic... #### \n')
    time.sleep(2)

    for x in range (21,30):
        user_svi_config = ['interface vlan' + ' ' + str(x),
                            'vrf member tenant-vrf-100',
                            'ip address 192.168.'+str(x)+'.254/24',
                            'fabric forwarding mode anycast-gateway',
                            'no shutdown']
        net_connect.send_config_set(user_svi_config)
    output = net_connect.send_command('show ip interface brief vrf tenant-vrf-100')
    print(output)
    time.sleep(3)
    net_connect.save_config()
