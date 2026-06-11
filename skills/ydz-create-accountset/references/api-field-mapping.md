# API Field Mapping

## Backend Source Fields

Public-manage backend task row:

| Source | Meaning | Target |
|---|---|---|
| `orgName` | Enterprise/customer name | `custName`, `corpName`, `accountBook.name` |
| `taxNo` | Tax number | `taxNo` |
| `taxAreaName` | Region name | Used for fallback area code |
| `loginJson.cLoginMethodEnum` | Login method code | `cLoginMethodEnum`, `taxLoginMethodEnum` |
| `loginJson.cSiteLoginName` | Proxy company tax number | `cSiteLoginName` for `DLYW-*` proxy login |
| `loginJson.cTaxPreparerName` | Privacy number for `YSHDL/DLYW-YSHDL`; phone/login account for `SDSRDX/DLYW-SDSRDX` | `cTaxPreparerName`, `realAccount` |
| `loginJson.cTaxPreparerPwd` | Personal user password | `cTaxPreparerPwd`, `realPwd` |

Remove a leading bracketed operator prefix from `orgName`, for example `[operator]Company` -> `Company`.

## Login Method Mapping

| UI Text | Code |
|---|---|
| 税局隐私号登录 | `YSHDL` |
| 税局隐私号-代理登录 | `DLYW-YSHDL` |
| Tax bureau manual captcha-code login | `SDSRDX` |
| Tax bureau manual captcha-code proxy login | `DLYW-SDSRDX` |

For all `DLYW-*` login methods, set `cSiteLoginName` to the proxy company tax number. For non-proxy methods, leave `cSiteLoginName` empty.

## Customer Create Payload

Endpoint:

```text
POST <ydz-base>/trans/easyacctg/customer/create
```

Required defaults:

| Page Field | Payload Field | Default |
|---|---|---|
| 客户名称 | `custName` | backend enterprise name |
| 企业名称 | `corpName` | same as customer name |
| 税号 | `taxNo` | user tax number |
| 启用期间 | `accountBook.openingPeriod` | `202501` |
| 纳税性质 | `accountBook.taxpayerTypeEnum`, `glAccountTaxpayerTypeEnum` | `SMALL_TAXPAYER` |
| 行业 | `taxIndustryId` | `11079` |
| 地区 | `taxiationArea` | resolved area code |
| 指派会计 | `accountantEmployeeId` | environment default |
| 是否建账 | `isBuild` | `true` |

Accountant note: `accountantEmployeeId` is resolved from the Yidaizhang employee list by matching the login phone to employee `mobile`. The saved value is the matched employee `userId`; if no match is available, the CLI falls back to current Yidaizhang `userId`, then the packaged environment default.

## Dynamic Tax Info Save

Endpoint:

```text
POST <ydz-base>/trans/easyacctg/taxInfo/saveCustTaxAndBusiInfo
```

Payload fields:

| Field | Value |
|---|---|
| `taxInfoDTO.easyacctgCustId` | created/existing customer ID |
| `taxInfoDTO.assocTenantId` | customer associated tenant ID |
| `taxInfoDTO.areaCode` | resolved area code |
| `taxInfoDTO.cLoginMethodEnum` | backend login method code |
| `taxInfoDTO.cSiteLoginName` | proxy tax number for `DLYW-*`, blank for non-proxy methods |
| `taxInfoDTO.cTaxPreparerName` | privacy number for `YSHDL/DLYW-YSHDL`; phone/login account for `SDSRDX/DLYW-SDSRDX` |
| `taxInfoDTO.cTaxPreparerPwd` | personal user password |
| `taxInfoDTO.cVerificationMethod` | `SYSTEM` |
| `taxInfoDTO.iVerificationMethod` | `SYSTEM` |
| `taxInfoDTO.isRpa` | `true` |
| `taxInfoDTO.isAuth` | `true` |

The UI reads this dynamic tax-info table. Customer create payload fields alone are not sufficient.

## Verification

Customer query:

```text
GET <ydz-base>/trans/easyacctg/customer/query
```

Tax-info query:

```text
POST <ydz-base>/trans/easyacctg/taxInfo/queryEasyacctgCustTaxInfo
```

Verify:

- Customer name, enterprise name, tax number.
- Opening period, taxpayer type, industry, accountant.
- Login method, proxy tax number, privacy number or phone/login account, personal password.

The accountant verification uses the resolved accountant id from the current run, not only the packaged fallback default.
