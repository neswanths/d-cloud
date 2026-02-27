{
  description = "Production Flake for D-Cloud App";

  inputs = {
    versions.url = "github:holochain/holochain?dir=versions/0_3";
    holonix.url = "github:holochain/holochain";
    holonix.inputs.versions.follows = "versions";
    nixpkgs.follows = "holonix/nixpkgs";
  };

  outputs = inputs:
    inputs.holonix.inputs.flake-parts.lib.mkFlake {
      inherit inputs;
    } {
      systems = builtins.attrNames inputs.holonix.devShells;
      perSystem = { pkgs, inputs', ... }: {
        devShells.default = pkgs.mkShell {
          inputsFrom = [ inputs'.holonix.devShells.default ];
          packages = [ pkgs.nodejs_20 pkgs.python3 ];
        };
      };
    };
}