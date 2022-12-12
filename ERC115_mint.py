
# import python modules
import os, sys, glob, time, requests, re, traceback, socket, base64
import subprocess, threading, json, argparse
import solcx
from web3 import Web3, middleware
#from compile import abi, bytecode
from dotenv import load_dotenv
from web3.exceptions import ContractLogicError
from web3.gas_strategies.time_based import *
from web3.middleware import geth_poa_middleware
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES, PKCS1_OAEP
# import traceback

from mainStream import focal

class ERC1155MintNFT:

    # main init function
    def __init__(self):
        load_dotenv()
        
        self.userDir  = os.path.expanduser('~')
        self.apiUrl   = os.getenv('API_URL')
        # print_exc
        # source meta mask address
        self.fromAddr = os.getenv('PUBLIC_KEY')
        # source meta mask private key
        self.pvtKey   = os.getenv('PRIVATE_KEY')

    # compile solidity file
    def compileSol( self ):
        # target file path
        source = "contracts/MintNFT_ERC1155.sol"

        # target filename
        file = "MintNFT_ERC1155.sol"

        # compiler specification
        spec = {
                "language": "Solidity",
                "sources": {
                    file: {
                        "urls": [
                            source
                        ]
                    }
                },
                "settings": {
                    "optimizer": {
                       "enabled": True
                    },
                    "outputSelection": {
                        "*": {
                            "*": [
                                "metadata", "evm.bytecode", "abi"
                            ]
                        }
                    }
                }
            };

        # catch output
        compileOut = solcx.compile_standard(spec, allow_paths=".")

        # Export contract data into variable
        abi = compileOut['contracts']['MintNFT_ERC1155.sol']['MintNFT_ERC1155']['abi']
        bytecode = compileOut['contracts']['MintNFT_ERC1155.sol']['MintNFT_ERC1155']['evm']['bytecode']['object']

        return abi, bytecode

    # deploy contract address
    def deployAddress( self, name, symbol ):
        print('deploying...')
        abi, bytecode = self.compileSol()

        # Web3 ETH provider
        self.web3 = Web3( provider=Web3.HTTPProvider( self.apiUrl ) )
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.web3.middleware_onion.add(middleware.time_based_cache_middleware)
        self.web3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
        self.web3.middleware_onion.add(middleware.simple_cache_middleware)

        focal.logger.info(f'Attempting to deploy from account: { self.fromAddr }')

        focal.logger.info(f'Attempting to deploy from account: { self.pvtKey }')

        # Create contract instance
        MintNFT_ERC1155 = self.web3.eth.contract( abi=abi, bytecode=bytecode )
        focal.logger.debug( f"{name}, {symbol}" )

        # Build constructor transaction
        
        constructTxn = MintNFT_ERC1155.constructor( name, symbol ).buildTransaction(
            {
                "gasPrice": self.web3.eth.gas_price,
                'from': self.fromAddr,
                'nonce': self.web3.eth.getTransactionCount( self.fromAddr ),
            }
        )

        # Sign transaction with Private Key
        txnCreate = self.web3.eth.account.signTransaction( constructTxn, self.pvtKey )

        # Send transaction and wait for receipt
        txnHash = self.web3.eth.sendRawTransaction( txnCreate.rawTransaction )
        txnReceipt = self.web3.eth.waitForTransactionReceipt( txnHash )

        focal.logger.info(f'Contract deployed at address: { txnReceipt.contractAddress }')

    def mintNFT( self, contractAddr, metaDataHash, editionCount ):
        abi, bytecode = self.compileSol()

        # Web3 ETH provider
        self.web3 = Web3( provider=Web3.HTTPProvider( self.apiUrl ) )

        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        contractArgs = [ self.fromAddr, editionCount,  f"ipfs://{metaDataHash}" ]
        fnName = "mint"

        contract = self.web3.eth.contract( contractAddr, abi=abi )
     
        contractData = contract.encodeABI( fnName, args=contractArgs )

        gas, gasprice, txnFee, nonce = self.calculateMandates( contract, fnName, contractArgs )

        tfrData = {
            'to': contract.address,
            'from': self.fromAddr,
            'value': Web3.toHex(0),
            'gasPrice': Web3.toHex(gasprice),
            'nonce': nonce,
            'data': contractData,
            'gas': Web3.toHex(gas),
        }

        focal.logger.info(f"Transaction:\n{tfrData}")
        focal.logger.info(f"Function: {fnName}")
        focal.logger.info(f"Arguments:{contractArgs}")
        focal.logger.info(f"Gas Price:{gasprice}")
        focal.logger.info(f"Gas:{gas}")
        focal.logger.info(f"Fees:{txnFee}")

        try:
            signed = self.web3.eth.account.signTransaction( tfrData, self.pvtKey )
            txn = self.web3.eth.sendRawTransaction( signed.rawTransaction )
            txnReceipt = self.web3.eth.waitForTransactionReceipt( txn )

            for key in txnReceipt:
                if key not in ['blockNumber','cumulativeGasUsed','from','contractAddress','status']:
                    continue

                val = txnReceipt.get(key)
                print(type(val))
                if( isinstance( val, bytes) ):
                    val = val.hex()

                focal.logger.info(f"{key}: %s ", (val,) )
        except Exception as e:
            focal.logger.info(f"{fnName} Error: ", e)

    def calculateMandates( self, contract, fnName, contractArgs ):

        # calculate gas & transaction fees
        csAddr = Web3.toChecksumAddress( self.fromAddr )

        strategy = construct_time_based_gas_price_strategy( 10 )

        self.web3.eth.setGasPriceStrategy( strategy )

        gas = getattr( contract.functions, fnName )(*contractArgs).estimateGas({'from': csAddr})

        gasprice = self.web3.eth.generateGasPrice()

        txnFee = gas * gasprice

        # calculate fees
        nonce = Web3.toHex( self.web3.eth.getTransactionCount(csAddr) )

        return gas, gasprice, txnFee, nonce

#---------------------------------------
# Setup arguments to execute
#---------------------------------------
def initOptions():
    csuc = focal.colors.get("success")
    cinf = focal.colors.get("info")
    cerr = focal.colors.get("error")
    cend = focal.colors.get("off")

    # Create the parser
    parser = argparse.ArgumentParser(
      prog="ERC1155 Mint NFT",
      allow_abbrev=False,
      description=f'{csuc}Process the choosen operation{cend}',
      epilog=f'{cinf}Am the helper of manage porting Rubix NFTs! (^_^){cend}'
    )

    # Mentaion the program version
    parser.version = '1.0'

    # Add the arguments
    parser.add_argument('-c', '--compile', nargs='?', const=True, type=bool, help='For compile the solidity')
    parser.add_argument('-d', '--deploy', nargs='?', const=True, type=bool, help='For deploy contract address')
    parser.add_argument('-m', '--mint', nargs='?', const=True, type=bool, help='For porting the Rubix NFT')
    parser.add_argument('-n', '--name', type=str, help='For name of the deployment group')
    parser.add_argument('-s', '--symbol', type=str, help='For symbol of the deployment group')
    parser.add_argument('-a', '--address', type=str, help='For address of the contract')
    parser.add_argument('-mh', '--metahash', type=str, help='For meta hash of the contract')
    parser.add_argument('-e', '--edition', type=int, help='For edition amount of the contract')
    parser.add_argument('-u', '--url', type=str, help='For API url of the blockchain')

    return parser

# httpRequest method
def httpRequest(url, method, data, headers = {}):
    responseData = None;

    try:
        focal.logger.info(f'Requesting the URL: {url}')

        response = requests.request(method.upper(), url, data = data, headers = headers)

        if response and response.ok:
            responseData = response.json()
    except Exception as e:
        focal.logger.error('Error while Requesting the URL:')

        focal.logger.error(traceback.format_exc())

    return responseData
# httpRequest method

#---------------------------------------
# Main method
#---------------------------------------
def main():
  try:
    mintNFT = ERC1155MintNFT()

    argparser = initOptions()

    argparser = focal.configParser( argparser )

    processes = {
                  "compile" : mintNFT.compileSol,
                  "deploy" : mintNFT.deployAddress,
                  "mint" : mintNFT.mintNFT,
                }

    args = argparser.parse_args()

    argprcd = focal.argProcess( argparser.parse_args() )

    if argprcd:
      exit()

    # Execute the parse_args() method
    args = vars(args)

    # call triggered process
    for call in processes.keys():
        if args[call]:
            func = processes[call]

            if call == 'mint':
                address = args['address']
                metahash = args['metahash']
                edition = args['edition']
                # apiUrl = args['url']

                func( address, metahash, edition )
            elif call == 'deploy':
                name = args['name']
                symbol = args['symbol']
                apiUrl = args['url']

                func( name, symbol)
            else:
                func()

  except Exception as err:
    # printing stack trace
    # traceback.print_exc()

    focal.logger.error(f"Error caught while process : {repr(err)}" )

    if focal.showLog:
      print(f'Oops...(>_<)')
  finally:
    if focal.showLog:
      exit(f'Bye...(^_^)')

# --------------------------------------------
# Main method declarations
# --------------------------------------------
if __name__ == '__main__':
  main()
