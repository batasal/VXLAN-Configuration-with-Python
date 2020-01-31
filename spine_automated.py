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

DEVICE_LIST = open('spine_device_list.txt')
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
        print ('\n #### Check to see if SSH is enabled on ' + DEVICE + ' ' + '#### \n')
        continue

    print ('\n #### Connection successfull, enabling VXLAN Spine related features... #### \n')
    features = [ 'feature ospf',
                    'feature bgp',
                    'feature pim',
                    'feature interface-vlan'
                    'feature nv overlay',
                    'nv overlay evpn \n' ]
    net_connect.send_config_set(features)
    print ('\n #### Features are successfully enabled #### \n')

    SPINE_IP_LIST = open('spine_ip_list.txt')
    for line in SPINE_IP_LIST:
        line_fields = line.split()
        hostname = line_fields[0]
        ip_1 = line_fields[1]
        ip_2 = line_fields[2]
        if hostname == DEVICE:
            spine_ip_config = ['interface loopback 0',
                                'ip address' + ' ' + ip_1  +'/32',
                                'description PIM_Anycast_IP_Address',
                                'ip router ospf UNDERLAY area 0.0.0.0',
                                'ip pim sparse-mode' ]
            net_connect.send_config_set(spine_ip_config)
            print('\n #### VTEP IP Address is configured on Loopback 0 #### \n')

            numbered_ip_config = ['interface loopback 100',
                                    'ip address' + ' ' + ip_2  +'/32',
                                    'description ip_to_be_used_as_unnumbered_on_p2p_links',
                                    'ip router ospf UNDERLAY area 0.0.0.0',
                                    'ip pim sparse-mode' ]
            net_connect.send_config_set(numbered_ip_config)
            print('\n #### Numbered IP Address is configured on Loopback 100 \n')

            output = net_connect.send_command('show ip interface brief')
            print(output)
            time.sleep(2)

            ospf_underlay_config = ['router ospf UNDERLAY',
                                    'router-id' + ' ' + ip_2 ,
                                    'log-adjacency-changes' ]
            net_connect.send_config_set(ospf_underlay_config)

            bgp_router_id_config = ['router bgp 65001',
                                    'router-id' +' '+ ip_2]
            net_connect.send_config_set(bgp_router_id_config)


            print("\n #### OSPF Process 'UNDERLAY' created #### \n")
            time.sleep(2)

            print('\n #### Configuring Leaf facing interfaces #### \n')
            leaf_int_config = ['interface ethernet 1/1-3',
                                'no switchport',
                                'mtu 9216',
                                'medium p2p',
                                'ip ospf network point-to-point',
                                'ip router ospf UNDERLAY area 0.0.0.0',
                                'ip pim sparse-mode',
                                'ip unnumbered loopback 100',
                                'no shutdown' ]
            net_connect.send_config_set(leaf_int_config)
            print('\n #### Leaf facing interface configuration is done #### \n')
            time.sleep(1)

            print('\n #### Configuring PIM Anycast RP settings #### \n')

            pim_rp_config = ['ip pim rp-address 1.1.1.190 group-list 225.12.0.0/16',
                                        'ip pim ssm range 232.0.0.0/8',
                                        'ip pim anycast-rp 1.1.1.190 1.1.100.191',
                                        'ip pim anycast-rp 1.1.1.190 1.1.100.192 \n' ]
            net_connect.send_config_set(pim_rp_config)

            print('\n #### Configuring BGP related settings #### \n')

            vtep_peer_list = open('vtep_ip_list.txt')
            for line in vtep_peer_list:
                line_fields = line.split()
                vtep_ip = line_fields[2]

                bgp_config = ['router bgp 65001',
                                    'address-family ipv4 unicast',
                                    'address-family l2vpn evpn',
                                    'template peer VTEP-PEER',
                                    'remote-as 65001',
                                    'update-source loopback 100',
                                    'address-family ipv4 unicast',
                                    'send-community both',
                                    'route-reflector-client',
                                    'exit',
                                    'address-family l2vpn evpn',
                                    'send-community both',
                                    'route-reflector-client',
                                    'exit',
                                    'neighbor' + ' ' + vtep_ip ,
                                    'inherit peer VTEP-PEER']
                net_connect.send_config_set(bgp_config)
                net_connect.save_config()
